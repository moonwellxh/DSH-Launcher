---
name: batch-files
description: >
  Expert-level Windows batch file (.bat/.cmd) skill for writing, debugging, and
  maintaining CMD scripts. Use when asked to "create a batch file", "write a
  .bat script", "automate a Windows task", "CMD scripting", "batch automation",
  "scheduled task script", "Windows shell script", or when working with .bat/.cmd
  files in the workspace. Covers cmd.exe syntax, environment variables, control
  flow, string processing, error handling, and integration with system tools.
  编写含中文的 .bat/.cmd 前，必须先载入 charset-pitfalls 技能（GBK+CRLF 编码约定）。
---

# Batch Files

A comprehensive skill for creating, editing, debugging, and maintaining Windows batch files (.bat/.cmd) using cmd.exe. Applies to CLI tool development, system administration automation, scheduled tasks, file operations scripting, and PATH-based executable scripts.

## 中文编码铁律（动手前必读）

**编写/修改任何 .bat/.cmd 之前，先载入 `charset-pitfalls` 技能**，并遵守：
- 含中文的 `.bat/.cmd` 必须 **GBK + CRLF、无 BOM**（UTF-8 无 BOM 会被 cmd.exe 按
  ANSI 代码页读成乱码/命令错乱）；
- 写文件用 `[System.Text.Encoding]::GetEncoding(936)`；
- 捕获 cmd 子进程输出按 GBK(936) 解码；
- 其余编码细节见 charset-pitfalls 技能，本技能不再重复。

## 配套维护提醒（dsh-launcher 一键启动技能）

本技能是 `dsh-launcher`（DSH 一键启动）的**配套技能**，已打包进其
`assets\配套技能\`，安装一键启动时会自动装上本技能。

**修改本技能后，三连同步（缺一不可）**：
1. 打包 `batch-files__skillhub.zip`（根目录=技能名）归档到 GitHub 仓库
   `releases\<当前版本>\`（zip 集中归档目录）＋更新配套源树 `dsh-launcher Add\batch-files\`；
2. 把新 zip 复制进 `dsh-launcher\assets\配套技能\`（覆盖旧包）；
3. 重打包 `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\` 并 git commit + push
   （setup.ps1 按时间戳自动分发新版；已弃用 Z: 盘存档）。

## When to Use This Skill

- Creating or editing `.bat` or `.cmd` files
- Automating Windows tasks (file operations, deployments, backups)
- Building CLI tools intended for a `bin/` folder on PATH
- Writing scheduled task scripts (SCHTASKS, Task Scheduler)
- Debugging batch script issues (variable expansion, error levels, quoting)
- Integrating batch scripts with external tools (curl, git, Node.js, Python)
- Scaffolding new batch-based projects with structured templates

## Prerequisites

- Windows NT-based OS (Windows 7 or later)
- cmd.exe (built-in)
- Optional: a `bin/` directory on PATH for distributing scripts as commands
- Optional: PATHEXT configured to include `.BAT;.CMD` (default on Windows)

## Command Interpretation

cmd.exe processes each line through four stages in order:

1. **Variable substitution** — `%VAR%` tokens are replaced with environment variable values. `%0`–`%9` reference batch arguments. `%*` expands to all arguments.
2. **Quoting and escaping** — Caret `^` escapes special characters (`& | < > ^`). Quotation marks prevent interpretation of enclosed special characters. In batch files, `%%` yields a literal `%`.
3. **Syntax parsing** — Lines are split into pipelines (`|`), compound commands (`&`, `&&`, `||`), and parenthesized groups `( )`.
4. **Redirection** — `>` overwrites, `>>` appends, `<` reads input, `2>` redirects stderr, `2>&1` merges stderr into stdout, `>NUL` discards output.

## Variables

### Environment Variables

```bat
set _MY_VAR=Hello World
echo %_MY_VAR%
set _MY_VAR=
```

- `set` with no arguments lists all variables
- `set _PREFIX` lists variables starting with `_PREFIX`
- No spaces around `=` — `set name = val` sets variable `"name "` to `" val"`

### Special Variables

| Variable | Value |
|----------|-------|
| `%CD%` | Current directory |
| `%DATE%` | System date (locale-dependent) |
| `%TIME%` | System time HH:MM:SS.mm |
| `%RANDOM%` | Pseudorandom number 0–32767 |
| `%ERRORLEVEL%` | Exit code of last command |
| `%USERNAME%` | Current user name |
| `%USERPROFILE%` | Current user profile path |
| `%TEMP%` / `%TMP%` | Temporary file directory |
| `%PATHEXT%` | Executable extensions list |
| `%COMSPEC%` | Path to cmd.exe |

### Scoping with SETLOCAL / ENDLOCAL

```bat
setlocal
set _LOCAL_VAR=scoped value
endlocal
REM _LOCAL_VAR is no longer defined here
```

To return a value from a scoped block:

```bat
endlocal & set _RESULT=%_LOCAL_VAR%
```

### Delayed Expansion

Variables inside parenthesized blocks are expanded at parse time. Use delayed expansion for runtime evaluation:

```bat
setlocal EnableDelayedExpansion
set _COUNT=0
for /l %%i in (1,1,5) do (
    set /a _COUNT+=1
    echo !_COUNT!
)
endlocal
```

- `!VAR!` expands at execution time (delayed)
- `%VAR%` expands at parse time (immediate)

## Control Flow

### Conditional Execution

```bat
if exist "output.txt" echo File found
if not defined _MY_VAR echo Variable not set
if "%_STATUS%"=="ready" (echo Go) else (echo Wait)
if %ERRORLEVEL% neq 0 echo Command failed
```

Comparison operators: `equ`, `neq`, `lss`, `leq`, `gtr`, `geq`. Use `/i` for case-insensitive string comparison.

### Compound Commands

```bat
command1 & command2        & REM Always run both
command1 && command2       & REM Run command2 only if command1 succeeds
command1 || command2       & REM Run command2 only if command1 fails
```

### FOR Loops

```bat
REM Iterate over a set of values
for %%i in (alpha beta gamma) do echo %%i

REM Numeric range: start, step, end
for /l %%i in (1,1,10) do echo %%i

REM Files in a directory
for %%f in (*.txt) do echo %%f

REM Recursive file search
for /r %%f in (*.log) do echo %%f

REM Directories only
for /d %%d in (*) do echo %%d

REM Parse command output
for /f "tokens=1,2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do echo %%b

REM Parse file lines
for /f "usebackq tokens=*" %%a in ("data.txt") do echo %%a
```

### GOTO and Labels

```bat
goto :main_logic
:usage
echo Usage: %~nx0 [options]
exit /b 1

:main_logic
echo Running main logic...
goto :eof
```

`goto :eof` exits the current batch or subroutine. Labels start with `:`.

## Command-Line Arguments

| Syntax | Value |
|--------|-------|
| `%0` | Script name as invoked |
| `%1`–`%9` | Positional arguments |
| `%*` | All arguments (unaffected by SHIFT) |
| `%~1` | Argument 1 with enclosing quotes removed |
| `%~f1` | Full path of argument 1 |
| `%~d1` | Drive letter of argument 1 |
| `%~p1` | Path (without drive) of argument 1 |
| `%~n1` | File name (no extension) of argument 1 |
| `%~x1` | Extension of argument 1 |
| `%~dp0` | Drive and path of the batch file itself |
| `%~nx0` | File name with extension of the batch file |
| `%~z1` | File size of argument 1 |
| `%~$PATH:1` | Search PATH for argument 1 |

### Argument Parsing Pattern

```bat
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="--output" (
    set "_OUTPUT_DIR=%~2"
    shift
)
shift
goto :parse_args
:args_done
```

## String Processing

### Substrings

```bat
set _STR=Hello World
echo %_STR:~0,5%       & REM "Hello"
echo %_STR:~6%         & REM "World"
echo %_STR:~-5%        & REM "World"
echo %_STR:~0,-6%      & REM "Hello"
```

### Search and Replace

```bat
set _STR=Hello World
echo %_STR:World=Earth%       & REM "Hello Earth"
echo %_STR:Hello=%            & REM " World" (remove "Hello")
```

### Substring Containment Test

```bat
if not "%_STR:World=%"=="%_STR%" echo Contains "World"
```

## Functions

Functions use labels, CALL, and SETLOCAL/ENDLOCAL:

```bat
@echo off
call :greet "Jane Doe"
echo Result: %_GREETING%
exit /b 0

:greet
setlocal
set "_MSG=Hello, %~1"
endlocal & set "_GREETING=%_MSG%"
exit /b 0
```

- `call :label args` invokes a function
- `exit /b` returns from the function (not the script)
- Use the `endlocal & set` trick to pass values out of a scoped block

## Arithmetic

`set /a` performs 32-bit signed integer arithmetic:

```bat
set /a _RESULT=10 * 5 + 3
set /a _COUNTER+=1
set /a _REMAINDER=14 %% 3       & REM Use %% for modulo in batch files
set /a _BITS="255 & 0x0F"       & REM Bitwise AND
```

Supported operators: `+ - * / %% ( )` and bitwise `& | ^ ~ << >>`.

Hexadecimal (`0xFF`) and octal (`077`) literals are supported.

## Error Handling

### Error Level Conventions

- `0` = success
- Non-zero = failure (typically `1`)

```bat
mycommand.exe
if %ERRORLEVEL% neq 0 (
    echo ERROR: mycommand failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
```

### Fail-Fast Pattern

```bat
command1 || (echo command1 failed & exit /b 1)
command2 || (echo command2 failed & exit /b 1)
```

### Setting Exit Codes

```bat
exit /b 0        & REM Return success from a batch/function
exit /b 1        & REM Return failure
cmd /c "exit /b 42"   & REM Set ERRORLEVEL to 42 inline
```

## Essential Commands Reference

### File Operations

| Command | Purpose |
|---------|---------|
| `DIR` | List directory contents |
| `COPY` | Copy files |
| `XCOPY` | Extended copy with subdirectories (legacy) |
| `ROBOCOPY` | Robust copy with retry, mirror, logging |
| `MOVE` | Move or rename files |
| `DEL` | Delete files |
| `REN` | Rename files |
| `MD` / `MKDIR` | Create directories |
| `RD` / `RMDIR` | Remove directories |
| `MKLINK` | Create symbolic or hard links |
| `ATTRIB` | View or set file attributes |
| `TYPE` | Print file contents |
| `MORE` | Paginated file display |
| `TREE` | Display directory structure |
| `REPLACE` | Replace files in destination with source |
| `COMPACT` | Show or set NTFS compression |
| `EXPAND` | Extract from .cab files |
| `MAKECAB` | Create .cab archives |
| `TAR` | Create or extract tar archives |

### Text Search and Processing

| Command | Purpose |
|---------|---------|
| `FIND` | Search for literal strings |
| `FINDSTR` | Search with limited regular expressions |
| `SORT` | Sort lines alphabetically |
| `CLIP` | Copy piped input to clipboard |
| `FC` | Compare two files |
| `COMP` | Binary file comparison |
| `CERTUTIL` | Encode/decode Base64, compute hashes |

### System Information

| Command | Purpose |
|---------|---------|
| `SYSTEMINFO` | Full system configuration |
| `HOSTNAME` | Display computer name |
| `VER` | Windows version |
| `WHOAMI` | Current user and group info |
| `TASKLIST` | List running processes |
| `TASKKILL` | Terminate processes |
| `WMIC` | WMI queries (drives, OS, memory) |
| `SC` | Service control (query, start, stop) |
| `DRIVERQUERY` | List installed drivers |
| `REG` | Registry operations (query, add, delete) |
| `SETX` | Set persistent environment variables |

### Network

| Command | Purpose |
|---------|---------|
| `PING` | Test network connectivity |
| `IPCONFIG` | IP configuration |
| `NSLOOKUP` | DNS lookup |
| `NETSTAT` | Network connections and ports |
| `TRACERT` | Trace route to host |
| `NET USE` | Map/disconnect network drives |
| `NET USER` | Manage user accounts |
| `NETSH` | Network configuration utility |
| `ARP` | ARP cache management |
| `ROUTE` | Routing table management |
| `CURL` | HTTP requests (Windows 10+) |
| `SSH` | Secure shell (Windows 10+) |

### Scheduling and Automation

| Command | Purpose |
|---------|---------|
| `SCHTASKS` | Create and manage scheduled tasks |
| `TIMEOUT` | Wait N seconds (Vista+) |
| `START` | Launch programs asynchronously |
| `RUNAS` | Run as different user |
| `SHUTDOWN` | Shutdown or restart |
| `FORFILES` | Find files by date and execute commands |

### Shell Utilities

| Command | Purpose |
|---------|---------|
| `WHERE` | Locate executables in PATH |
| `DOSKEY` | Create command macros |
| `CHOICE` | Prompt for single-key input |
| `MODE` | Configure console size and ports |
| `SUBST` | Map folder to drive letter |
| `CHCP` | Get or set console code page |
| `COLOR` | Set console colors |
| `TITLE` | Set console window title |
| `ASSOC` / `FTYPE` | File type associations |

## Shell Syntax and Expressions

### Parentheses for Grouping

Parentheses turn compound commands into a single unit for redirection or conditional execution:

```bat
(echo Line 1 & echo Line 2) > output.txt
if exist "data.csv" (
    echo Processing...
    call :process "data.csv"
) else (
    echo No data found.
)
```

### Escape Characters

The caret `^` escapes the next character:

```bat
echo Total ^& Summary          & REM Outputs: Total & Summary
echo 100%% complete            & REM Outputs: 100% complete (in batch)
echo Line one^
Line two                       & REM Caret escapes the newline
```

After a pipe, triple caret is needed: `echo x ^^^& y | findstr x`

### Wildcards

- `*` matches any sequence of characters
- `?` matches a single character (or zero at end of period-free segment)

```bat
dir *.txt           & REM All .txt files
ren *.jpeg *.jpg    & REM Bulk rename
```

### Redirection Summary

```bat
command > file.txt          & REM Overwrite stdout to file
command >> file.txt         & REM Append stdout to file
command 2> errors.log       & REM Redirect stderr
command > all.log 2>&1      & REM Merge stderr into stdout
command < input.txt         & REM Read stdin from file
command > NUL 2>&1          & REM Discard all output
```

## Writing Production-Quality Batch Files

### Standard Script Structure

```bat
@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  Script: example.bat
REM  Purpose: Describe what this script does
REM ============================================================

call :main %*
exit /b %ERRORLEVEL%

:main
    call :parse_args %*
    if not defined _TARGET (
        echo ERROR: --target is required. 1>&2
        call :usage
        exit /b 1
    )
    echo Processing: %_TARGET%
    exit /b 0

:parse_args
    if "%~1"=="" exit /b 0
    if /i "%~1"=="--target" set "_TARGET=%~2" & shift
    if /i "%~1"=="--help"   call :usage & exit /b 0
    shift
    goto :parse_args

:usage
    echo Usage: %~nx0 --target ^<path^> [--help]
    echo.
    echo Options:
    echo   --target   Path to process (required)
    echo   --help     Show this help message
    exit /b 0
```

### Best Practices

1. **Always start with `@echo off` and `setlocal`** — Prevents noisy output and variable leakage to the caller.
2. **Validate inputs before processing** — Check required arguments and file existence early. Use `if not defined` and `if not exist`.
3. **Quote paths and variables** — Use `"%~1"` and `"%_MY_PATH%"` to handle spaces and special characters safely.
4. **Use `exit /b` instead of `exit`** — Avoids closing the parent console window.
5. **Return meaningful exit codes** — `exit /b 0` for success, non-zero for specific failures.
6. **Use `%~dp0` for script-relative paths** — Ensures the script works regardless of the caller's working directory.
7. **Prefer `ROBOCOPY` over `XCOPY`** — More reliable, supports retry, mirroring, and logging.
8. **Use `EnableDelayedExpansion` when modifying variables inside loops or parenthesized blocks.**
9. **Write errors to stderr** — `echo ERROR: message 1>&2` keeps stdout clean for piping.
10. **Use `REM` for comments** — `::` can cause issues inside `FOR` loop bodies.

### Security Considerations

- **Never store credentials in batch files** — Use environment variables, credential stores, or prompts.
- **Validate user input** — Unquoted variables containing `&`, `|`, or `>` can inject commands. Always quote: `"%_USER_INPUT%"`.
- **Use `SETLOCAL`** — Prevents variable values from leaking to parent processes.
- **Sanitize file paths** — Validate paths before passing to `DEL`, `RD`, or `ROBOCOPY` to prevent unintended deletion.
- **Avoid `SET /P` for sensitive input** — Input is visible and stored in console history. Use a dedicated credential tool when possible.

## Debugging and Troubleshooting

| Technique | How |
|-----------|-----|
| Trace execution | Remove `@echo off` or use `@echo on` temporarily |
| Step through | Add `PAUSE` between sections |
| Check error level | `echo Exit code: %ERRORLEVEL%` after each command |
| Inspect variables | `set _MY_` to list all variables starting with `_MY_` |
| Delayed expansion issues | Variable inside `( )` block not updating? Enable `!VAR!` syntax |
| FOR loop `%%` vs `%` | Use `%%i` in batch files, `%i` on the command line |
| Spaces in SET | `set name=value` not `set name = value` |
| Caret in pipes | After a pipe, use `^^^` to escape special chars |
| Parentheses in SET /A | Escape with `^(` and `^)` inside `if` blocks, or use quotes |
| Double percent for modulo | `set /a r=14 %% 3` in batch files |
| Command runs the wrong file | cmd 解析命令**当前目录优先于 PATH**——工作目录有同名 `.cmd/.bat/.exe` 会劫持裸命令名（见下节红线） |

### ⚠ 当前目录优先于 PATH（目录劫持）——防复发红线（2026-08-23）

cmd.exe 解析命令时**当前目录优先于 PATH**：只要工作目录里存在同名
`.cmd/.bat/.exe`（含 `%~dp0` 所在目录、`start`/快捷方式继承的 CWD），裸命令名就会被它
劫持，而不是解析到 PATH 上的全局命令。

**实战事故（dsh-launcher 托盘 15s 循环 Bug）**：托盘内部 `cmd /c dsh web` 想启动 web
服务，但安装目录里正好有本地 `dsh.cmd` 包装器（其 `web` 分支是"再拉起一个托盘"）→
服务永远起不来，反而每 15s 拉起一个新托盘、旧托盘被互斥锁强杀（鬼影图标）无限循环。
修复 = 内部调用一律用**绝对路径**：`cmd /c "<全局入口绝对路径>" web`。

**红线（写任何 .bat/.cmd 都遵守）**：
1. 脚本**内部**调用入口/服务/命令时，一律用解析出的**绝对路径**，禁止裸命令名
   （除非确认工作目录绝无同名文件，且不依赖 CWD）；
2. 拼路径用 `%~dp0`（自带结尾反斜杠）；转发入口用 `call "<绝对路径>" %*`；
3. 排查"命令没生效/循环/鬼影图标/点了没反应"时，先查：① 内部调用是否裸命令名；
   ② cmd 当前目录（快捷方式 WorkingDirectory、`start` 继承 CWD）里是否有同名文件；
   ③ `where <命令>` 实际解析到谁。

## Cross-Platform and Extended Tools

When batch scripting reaches its limits, these tools extend cmd.exe capabilities:

| Tool | Purpose |
|------|---------|
| **Cygwin** | Full POSIX environment on Windows (grep, sed, awk, ssh) |
| **MSYS2** | Lightweight Unix tools and package manager (pacman) |
| **WSL** | Windows Subsystem for Linux — run native Linux binaries |
| **GnuWin32** | Individual GNU utilities as native Windows executables |
| **PowerShell** | Modern Windows scripting with .NET integration |

Use batch when you need: fast startup, simple file operations, PATH-based CLI tools, or Task Scheduler integration. Consider PowerShell or WSL for complex data processing, REST APIs, or object-oriented scripting.

## CMD Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Tab` | Auto-complete file/folder names |
| `Up` / `Down` | Navigate command history |
| `F7` | Show command history popup |
| `F3` | Repeat last command |
| `Esc` | Clear current line |
| `Ctrl+C` | Cancel running command |
| `Alt+F7` | Clear command history |

## Reference Files

The `references/` folder contains detailed documentation:

| File | Contents |
|------|----------|
| `tools-and-resources.md` | Windows tools, utilities, package managers, terminals |
| `batch-files-and-functions.md` | Example scripts, techniques, best practices links |
| `windows-commands.md` | Comprehensive A-Z Windows command reference |
| `cygwin.md` | Cygwin user guide and FAQ |
| `msys2.md` | MSYS2 installation, packages, and environments |
| `windows-subsystem-on-linux.md` | WSL setup, commands, and documentation |

## Asset Templates

The `assets/` folder contains starter batch file templates:

| Template | Purpose |
|----------|---------|
| `executable.bat` | Standalone CLI tool with argument parsing |
| `library.bat` | Reusable function library with CALL-able labels |
| `task.bat` | Scheduled task / automation script |
