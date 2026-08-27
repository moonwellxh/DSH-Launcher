// ======================================================================
// TZ3Converter - Tianzheng T3 silent converter (AutoCAD .NET plugin)
// Robust version: dynamically resolves SaveAsTArch3 export + reads DWG
// version from file header, so it adapts to any DWG version / Tianzheng
// version (V7/V8/...) without recompiling.
//
// rev2 changes (2026-08-17):
//   - atomic write: save to 原名_AiT3.dwg.tmp first, then File.Move(tmp, 正式)
//     (prevents half-written file being mistaken as "updated" after a crash)
//   - machine-readable result line: "[TZ3-OK] <path>" on success
//
// Usage: NETLOAD this dll, then type TZ3.
// ======================================================================
using System;
using System.IO;
using System.Runtime.InteropServices;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(TZ3Converter.TZ3))]

namespace TZ3Converter
{
    public class TZ3
    {
        // int SaveAsTArch3(AcDbDatabase*, wchar_t* path, int progId, bool)
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        delegate int SaveAsTArch3Delegate(IntPtr db,
            [MarshalAs(UnmanagedType.LPWStr)] string path, int progId, bool param2);

        [CommandMethod("TZ3", CommandFlags.Modal)]
        public void Tz3()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor;
            var db = doc.Database;

            string src = db.Filename;
            if (string.IsNullOrEmpty(src) || !File.Exists(src))
            {
                ed.WriteMessage("\n[TZ3] current drawing not saved, save it first");
                return;
            }

            string outFile = Path.Combine(
                Path.GetDirectoryName(src),
                Path.GetFileNameWithoutExtension(src) + "_AiT3.dwg");

            // atomic write: write .tmp first, rename to final on success
            string tmpFile = outFile + ".tmp";
            try { if (File.Exists(tmpFile)) File.Delete(tmpFile); } catch { }

            // 1. dynamic resolve SaveAsTArch3 from tch_kernal.arx (works across Tianzheng versions)
            IntPtr fnAddr = FindExportByName("tch_kernal.arx", "SaveAsTArch3");
            if (fnAddr == IntPtr.Zero)
            {
                ed.WriteMessage("\n[TZ3] SaveAsTArch3 not found in tch_kernal.arx");
                return;
            }

            // 2. progId from DWG file header (shared-read to bypass AutoCAD lock)
            int progId = GetProgIdFromFile(src, db.OriginalFileVersion);
            ed.WriteMessage("\n[TZ3] progId=" + progId + " -> " + outFile);

            // 3. invoke (write to .tmp)
            try
            {
                var fn = (SaveAsTArch3Delegate)Marshal.GetDelegateForFunctionPointer(
                    fnAddr, typeof(SaveAsTArch3Delegate));
                int ret = fn(db.UnmanagedObject, tmpFile, progId, false);
                if (File.Exists(tmpFile))
                {
                    try
                    {
                        File.Move(tmpFile, outFile);
                        ed.WriteMessage("\n[TZ3-OK] " + outFile);
                    }
                    catch (System.Exception exMove)
                    {
                        ed.WriteMessage("\n[TZ3] rename failed: " + exMove.Message
                            + " (tmp kept at " + tmpFile + ")");
                    }
                }
                else
                {
                    ed.WriteMessage("\n[TZ3] return=" + ret + " but no output file");
                }
            }
            catch (System.Exception ex)
            {
                ed.WriteMessage("\n[TZ3] failed: " + ex.GetType().Name + ": " + ex.Message);
            }
        }

        // read DWG file header version string ("AC1015"/"AC1018"/...) -> progId
        // uses FileShare.ReadWrite so it works even while AutoCAD locks the file
        static int GetProgIdFromFile(string path, DwgVersion fallback)
        {
            try
            {
                byte[] buf = new byte[6];
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    if (fs.Read(buf, 0, 6) < 6) return GetProgIdFromEnum(fallback);
                }
                string tag = System.Text.Encoding.ASCII.GetString(buf);
                switch (tag)
                {
                    case "AC1009": return 12; // R12
                    case "AC1012": return 13; // R13
                    case "AC1014": return 14; // R14
                    case "AC1015": return 15; // 2000
                    case "AC1018": return 16; // 2004
                    case "AC1021": return 17; // 2007
                    case "AC1024": return 18; // 2010
                    case "AC1027": return 19; // 2013
                    case "AC1032": return 23; // 2018+
                    default: return GetProgIdFromEnum(fallback);
                }
            }
            catch { return GetProgIdFromEnum(fallback); }
        }

        // fallback: map .NET DwgVersion enum (note: 2004 is AC1800 in this enum)
        static int GetProgIdFromEnum(DwgVersion ver)
        {
            switch (ver)
            {
                case DwgVersion.AC1015: return 15; // 2000
                case DwgVersion.AC1800: return 16; // 2004
                case DwgVersion.AC1021: return 17; // 2007
                case DwgVersion.AC1024: return 18; // 2010
                case DwgVersion.AC1027: return 19; // 2013
                case DwgVersion.AC1032: return 23; // 2018+
                default: return 23;
            }
        }

        // ============ dynamic export resolution ============
        [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
        static extern IntPtr LoadLibrary(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Ansi)]
        static extern IntPtr GetModuleHandle(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Ansi)]
        static extern IntPtr GetProcAddress(IntPtr hModule, string name);

        // walk PE export table of a loaded module, return address of export whose name contains `keyword`
        static IntPtr FindExportByName(string dllName, string keyword)
        {
            IntPtr hModule = GetModuleHandle(dllName);
            if (hModule == IntPtr.Zero)
                hModule = LoadLibrary(dllName);
            if (hModule == IntPtr.Zero)
                return IntPtr.Zero;

            try
            {
                long baseAddr = hModule.ToInt64();

                // DOS header -> e_lfanew
                int e_lfanew = ReadInt32(baseAddr + 0x3C);
                long pe = baseAddr + e_lfanew;

                // optional header magic
                short magic = ReadInt16(pe + 24);
                long opt = pe + 24;
                long dataDir = opt + (magic == 0x20b ? 112 : 96);

                // export directory (first data directory entry)
                int exportRva = ReadInt32(dataDir);
                if (exportRva == 0)
                    return IntPtr.Zero;

                long exp = baseAddr + exportRva;
                int nNames = ReadInt32(exp + 24);
                int addrNamesRva = ReadInt32(exp + 32);

                for (int i = 0; i < nNames; i++)
                {
                    int nameRva = ReadInt32(baseAddr + addrNamesRva + i * 4);
                    string name = ReadAsciiString(baseAddr + nameRva, 256);
                    if (name != null && name.Contains(keyword))
                    {
                        return GetProcAddress(hModule, name);
                    }
                }
            }
            catch { }
            return IntPtr.Zero;
        }

        static short ReadInt16(long addr)
        {
            byte[] b = new byte[2];
            Marshal.Copy(new IntPtr(addr), b, 0, 2);
            return BitConverter.ToInt16(b, 0);
        }

        static int ReadInt32(long addr)
        {
            byte[] b = new byte[4];
            Marshal.Copy(new IntPtr(addr), b, 0, 4);
            return BitConverter.ToInt32(b, 0);
        }

        static string ReadAsciiString(long addr, int maxLen)
        {
            byte[] b = new byte[maxLen];
            Marshal.Copy(new IntPtr(addr), b, 0, maxLen);
            int len = 0;
            while (len < maxLen && b[len] != 0) len++;
            return System.Text.Encoding.ASCII.GetString(b, 0, len);
        }
    }
}
