// l0_checks.js
// 作用：对 消防隐患联合排查整治行动情况登记表（竹箦/薛埠）成品做确定性校验（零模型判断）：
//   c1 行数/逐行内容与源docx重放一致；c2 序号连续；c3 专业序非递减；c4 L/N∈下拉词表；
//   c5 属性与"其他信息"一致；c6 合并区域无重叠且完整；c7 非法字符；c8 P备注全空；c9 ht合法。
// 输入：成品两份xlsx、源docx目录(21份)、其他信息两份xlsx
// 输出：stdout JSON 报告（pass/fail+锚点明细）
// 复跑：node l0_checks.js
'use strict';
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const ROOT = 'C:/Users/雍远/Desktop/Jy/ＰＩＣ/消防审验意见/27竹箦28薛埠防查验意见汇总';
const CONV = path.join(process.env.TEMP || 'C:/Windows/Temp', 'lo_conv');

function readZip(file) {
  const buf = fs.readFileSync(file);
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 65536); i--) {
    if (buf[i] === 0x50 && buf[i+1] === 0x4b && buf[i+2] === 0x05 && buf[i+3] === 0x06) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('EOCD not found in ' + file);
  const cdCount = buf.readUInt16LE(eocd + 10);
  let off = buf.readUInt32LE(eocd + 16);
  const entries = [];
  for (let n = 0; n < cdCount; n++) {
    if (buf.readUInt32LE(off) !== 0x02014b50) throw new Error('bad central header');
    const method = buf.readUInt16LE(off + 10);
    const compSize = buf.readUInt32LE(off + 20);
    const nameLen = buf.readUInt16LE(off + 28);
    const extraLen = buf.readUInt16LE(off + 30);
    const commentLen = buf.readUInt16LE(off + 32);
    const lho = buf.readUInt32LE(off + 42);
    const name = buf.toString('utf8', off + 46, off + 46 + nameLen);
    const lNameLen = buf.readUInt16LE(lho + 26);
    const lExtraLen = buf.readUInt16LE(lho + 28);
    const dataStart = lho + 30 + lNameLen + lExtraLen;
    const comp = buf.slice(dataStart, dataStart + compSize);
    let data;
    if (method === 0) data = comp;
    else if (method === 8) data = zlib.inflateRawSync(comp);
    else throw new Error('zip method ' + method);
    entries.push({ name, data });
    off += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}

function elemRange(xml, tag, from, prefix) {
  if (prefix === undefined) prefix = 'w:';
  const re = new RegExp('<' + prefix + tag + '(?:\\s[^>]*)?>', 'g');
  re.lastIndex = from;
  const m = re.exec(xml);
  if (!m) return null;
  const openEnd = m.index + m[0].length;
  const openRe = new RegExp('<' + prefix + tag + '(?:\\s[^>]*)?>', 'g');
  const closeRe = new RegExp('</' + prefix + tag + '>', 'g');
  openRe.lastIndex = openEnd; closeRe.lastIndex = openEnd;
  let depth = 1, b = -1;
  for (let g = 0; g < 5000000; g++) {
    const na = openRe.exec(xml), nb = closeRe.exec(xml);
    if (!na && !nb) break;
    if (nb && (!na || nb.index < na.index)) { depth--; b = nb.index + nb[0].length; if (depth === 0) break; }
    else if (na) depth++;
    else break;
  }
  if (b < 0) return null;
  return { start: m.index, end: b, innerStart: openEnd, innerEnd: b - ('</' + prefix + tag + '>').length };
}
function elemRangesAll(xml, tag, prefix) {
  if (prefix === undefined) prefix = 'w:';
  const out = []; let from = 0;
  for (let g = 0; g < 200000; g++) {
    const r = elemRange(xml, tag, from, prefix);
    if (!r) break;
    out.push(r); from = r.end;
  }
  return out;
}
function stripTags(s) { return s.replace(/<[^>]+>/g, ''); }
function decodeEntities(s) {
  return s.replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&').replace(/&#(\d+);/g, (m, d) => String.fromCharCode(parseInt(d, 10))).replace(/&#x([0-9a-fA-F]+);/g, (m, d) => String.fromCharCode(parseInt(d, 16)));
}
function docxText(xml) {
  let s = xml.replace(/<w:p\b[^>]*>/g, '\n').replace(/<\/w:p>/g, '');
  s = s.replace(/<w:tab\b[^>]*\/?>/g, '\t').replace(/<w:br\b[^>]*\/?>/g, '\n');
  s = s.replace(/<w:drawing\b[\s\S]*?<\/w:drawing>/g, '').replace(/<w:pict\b[\s\S]*?<\/w:pict>/g, '').replace(/<w:object\b[\s\S]*?<\/w:object>/g, '');
  s = s.replace(/<w:txbxContent\b[\s\S]*?<\/w:txbxContent>/g, '');
  s = stripTags(s).replace(/\r/g, '');
  s = s.split('\n').map(x => x.trim()).filter(x => x.length > 0).join('\n');
  return decodeEntities(s);
}
function parseDocx(file) {
  const entries = readZip(file);
  const doc = entries.find(e => e.name === 'word/document.xml');
  if (!doc) return { issues: [] };
  const xml = doc.data.toString('utf8');
  const issues = [];
  for (const t of elemRangesAll(xml, 'tbl')) {
    const tblXml = xml.slice(t.innerStart, t.innerEnd);
    const hdrTxt = docxText(tblXml).split('\n').find(l => l.includes('问题描述'));
    if (!hdrTxt) continue;
    for (const r of elemRangesAll(tblXml, 'tr')) {
      const trXml = tblXml.slice(r.innerStart, r.innerEnd);
      const cells = elemRangesAll(trXml, 'tc').map(c => docxText(trXml.slice(c.innerStart, c.innerEnd)).replace(/\s*\n\s*/g, '\n').trim());
      if (cells.length < 4) continue;
      const desc = cells[2] || '';
      if (!desc || /问题描述/.test(desc)) continue;
      issues.push({ zy: cells[1] || '', desc, clause: cells[3] || '', suggest: cells.length > 5 ? (cells[5] || '') : '' });
    }
    if (issues.length) break;
  }
  return { issues };
}
function parseAttrXlsx(file) {
  const entries = readZip(file);
  const ssEntry = entries.find(e => e.name === 'xl/sharedStrings.xml');
  const ss = [];
  if (ssEntry) {
    const xml = ssEntry.data.toString('utf8');
    for (const si of elemRangesAll(xml, 'si', '')) ss.push(decodeEntities(stripTags(xml.slice(si.innerStart, si.innerEnd))));
  }
  const shEntry = entries.find(e => /worksheets\/sheet1\.xml$/.test(e.name));
  if (!shEntry) return [];
  const xml = shEntry.data.toString('utf8');
  const list = [];
  for (const row of elemRangesAll(xml, 'row', '')) {
    const rowXml = xml.slice(row.innerStart, row.innerEnd);
    const col = {};
    const cre = /<c\b([^>]*?)(\/?)>/g;
    let m;
    while ((m = cre.exec(rowXml)) !== null) {
      const attrs = m[1];
      const refM = /r="([A-Z]+)\d+"/.exec(attrs);
      if (!refM) continue;
      const ref = refM[1];
      const selfClose = m[2] === '/';
      const tM = / t="([^"]+)"/.exec(attrs);
      let v = '';
      if (!selfClose) {
        const innerStart = cre.lastIndex;
        const closeIdx = rowXml.indexOf('</c>', innerStart);
        if (closeIdx >= 0) {
          const inner = rowXml.slice(innerStart, closeIdx);
          if (tM && tM[1] === 'inlineStr') {
            const is = /<is>([\s\S]*?)<\/is>/.exec(inner);
            if (is) v = decodeEntities(stripTags(is[1]));
          } else {
            const vm = /<v>([\s\S]*?)<\/v>/.exec(inner);
            if (vm) v = (tM && tM[1] === 's') ? (ss[parseInt(vm[1], 10)] || '') : vm[1];
          }
          cre.lastIndex = closeIdx + 4;
        }
      }
      col[ref] = decodeEntities(v).trim();
    }
    if (col.A && /^\d+$/.test(col.A) && col.C) {
      list.push({ idx: parseInt(col.A, 10), name: col.C, purpose: col.D || '', nowUse: col.E || '', area: col.F || '', footprint: col.G || '', year: col.H || '', approval: col.I || '' });
    }
  }
  return list;
}
function parseSheetXml(xml) {
  const rows = [];
  const re = /<row\b([^>]*)>([\s\S]*?)<\/row>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const rnM = /r="(\d+)"/.exec(m[1]);
    const rn = parseInt(rnM[1], 10);
    const htM = /ht="([\d.]+)"/.exec(m[1]);
    const cells = {};
    const cre = /<c\b([^>]*?)(\/?)>/g;
    let cm;
    const body = m[2];
    while ((cm = cre.exec(body)) !== null) {
      const attrs = cm[1];
      const refM = /r="([A-Z]+)(\d+)"/.exec(attrs);
      if (!refM) continue;
      const colLetter = refM[1];
      if (cells[colLetter]) continue;
      const selfClose = cm[2] === '/';
      const tM = / t="([^"]+)"/.exec(attrs);
      let v = '';
      if (!selfClose) {
        const innerStart = cre.lastIndex;
        const closeIdx = body.indexOf('</c>', innerStart);
        if (closeIdx >= 0) {
          const inner = body.slice(innerStart, closeIdx);
          if (tM && tM[1] === 'inlineStr') {
            const is = /<is>([\s\S]*?)<\/is>/.exec(inner);
            if (is) v = decodeEntities(stripTags(is[1]).replace(/&#10;/g, '\n'));
          } else {
            const vm = /<v>([\s\S]*?)<\/v>/.exec(inner);
            if (vm) v = vm[1];
          }
          cre.lastIndex = closeIdx + 4;
        }
      }
      cells[colLetter] = v;
    }
    rows.push({ rn, ht: htM ? parseFloat(htM[1]) : null, cells });
  }
  rows.sort((a, b) => a.rn - b.rn);
  const merges = [];
  const mr = /<mergeCell ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"/g;
  while ((m = mr.exec(xml)) !== null) merges.push([m[1], parseInt(m[2], 10), m[3], parseInt(m[4], 10)]);
  return { rows, merges };
}
function normName(s) { if (!s) return ''; return s.replace(/[（(].*?[）)]/g, '').replace(/[#＃\s]/g, '').trim(); }
function findAttr(attrs, name) {
  const n = normName(name);
  for (const a of attrs) {
    const an = normName(a.name);
    if (an && (an.startsWith(n) || n.startsWith(an))) return a;
  }
  return null;
}
function canonZy(zy) {
  if (/建筑/.test(zy)) return '建筑';
  if (/给排水|水/.test(zy)) return '给排水';
  if (/电气|电/.test(zy)) return '电气';
  if (/暖通|通风/.test(zy)) return '暖通';
  return zy.trim();
}
const RANK = { '建筑': 0, '给排水': 1, '电气': 2, '暖通': 3 };
function rankOf(zy) { const k = Object.keys(RANK).find(kk => zy.includes(kk)); return k ? RANK[k] : 9; }
function skipRow(d) { return /无查验意义|无问题。|现场仅余建筑构造|一层现为卫生室/.test(d); }
function clean(s) {
  return String(s || '').replace(/\r/g, '').replace(/\[IMG\]|\[PICT\]/g, '')
    .split('\n').map(x => x.replace(/\s+/g, ' ').trim()).join('\n').replace(/\n{2,}/g, '\n')
    .replace(/\s*[\/、；;]+\s*$/g, '');
}
function numEq(a, b) {
  const na = parseFloat(a), nb = parseFloat(b);
  if (isNaN(na) || isNaN(nb)) return String(a).trim() === String(b).trim();
  return Math.abs(Math.round(na * 100) / 100 - Math.round(nb * 100) / 100) < 0.005;
}

const ALLOWED_L = new Set(['消防车道类','防火分区类','疏散通道类','消火栓系统类','自动喷水灭火系统类','火灾自动报警及联动控制系统类','防排烟与通风防火设施类','疏散指示标志系统类','消防供配电类','建筑装修耐火保温类','气体灭火系统类','消防水泵类','灭火器及消防器材配置类','危险化学品安全管理类','电动自行车消防安全类','伙房厨房燃气安全类','建筑使用功能变更与违建类','建筑结构安全类','其他']);
const ALLOWED_N = new Set(['必须整改','建议整改','加强管理']);
// R2 评审批准修订白名单（2026-09-07）：desc 勘误 + 制茶楼用途（用户裁决）
const DESC_OVERRIDES = {
  '竹箦|2号厂房|1': '仓库未设置防火门',
  '竹箦|制茶楼|7': '消火栓箱内皆无消火栓按钮',
  '薛埠|1号总仓|3': '楼梯内有可燃杂物',
  '薛埠|1号总仓|7': '报警阀的警铃设置报警阀房间内。',
  '薛埠|伙房|1': '库房采用玻璃隔断与厨房分隔，防火分隔不足2h',
  '薛埠|民警综合楼|4': '消控室连接的楼梯在一层未外开'
};
const BUILDING_OVERRIDES = { '竹箦|制茶楼': { D: '丙类仓储' } };

const targets = [
  { prison: '竹箦', unit: '竹箦分监狱', recDir: '竹箦消防查验意见汇总', attrFile: ROOT + '/其他信息/消防隐患联合排查整治行动情况登记表竹箦.xlsx', outFile: ROOT + '/消防隐患联合排查整治行动情况登记表 - 竹箦.xlsx' },
  { prison: '薛埠', unit: '薛埠分监狱', recDir: '薛埠消防查验意见汇总', attrFile: ROOT + '/其他信息/消防隐患联合排查整治行动情况登记表薛埠.xlsx', outFile: ROOT + '/消防隐患联合排查整治行动情况登记表 - 薛埠.xlsx' }
];

const report = [];
let totalFails = 0;
for (const t of targets) {
  const fails = [];
  const attrs = parseAttrXlsx(t.attrFile);
  // expected rows replay from docx
  const recDir = ROOT + '/' + t.recDir;
  const files = fs.readdirSync(recDir).filter(f => /\.(docx|doc)$/i.test(f)).sort();
  const expected = [];
  for (const fn of files) {
    let src = path.join(recDir, fn);
    if (/\.doc$/i.test(fn)) {
      const conv = path.join(CONV, fn.replace(/\.doc$/i, '.docx'));
      if (fs.existsSync(conv)) src = conv;
    }
    let name = fn.replace(/^消防安全隐患问题排查-现场记录表（/, '').replace(/）\s*\.(docx|doc)$/i, '').replace(/^.*?分监狱-/, '').replace(/[–—-]?\d{1,2}[–—-]\d{1,2}$/, '');
    const parsed = parseDocx(src);
    const keep = parsed.issues.filter(r => !skipRow(r.desc));
    const sorted = keep.slice().sort((x, y) => rankOf(x.zy) - rankOf(y.zy));
    const attr = findAttr(attrs, name);
    expected.push({ fn, name, attr, rows: sorted });
  }
  // order buildings by attr idx (like plan)
  expected.sort((a, b) => (a.attr ? a.attr.idx : 999) - (b.attr ? b.attr.idx : 999));
  // read final sheet
  const outEntries = readZip(t.outFile);
  const sh = outEntries.find(e => e.name === 'xl/worksheets/sheet1.xml');
  const { rows, merges } = parseSheetXml(sh.data.toString('utf8'));
  const dataRows = rows.filter(r => r.rn >= 4);
  const byRn = {}; for (const r of dataRows) byRn[r.rn] = r;

  // c1 building count & row counts & per-row content
  const expBuildings = expected.filter(b => b.rows.length > 0);
  const gotBlocks = dataRows.filter(r => (r.cells.B || '') !== '').map(r => r.rn);
  if (expBuildings.length !== gotBlocks.length) fails.push({ check: 'building_count', anchor: 'sheet row4..end', detail: '期望建筑数=' + expBuildings.length + ' 成品块数=' + gotBlocks.length });
  let rn = 3;
  for (let bi = 0; bi < expBuildings.length; bi++) {
    const b = expBuildings[bi];
    const bStart = rn + 1;
    for (let k = 0; k < b.rows.length; k++) {
      rn++;
      const r = b.rows[k];
      const got = byRn[rn];
      if (!got) { fails.push({ check: 'row_missing', anchor: 'row ' + rn, detail: b.name + ' 期望行缺失' }); continue; }
      const oid = t.prison + '|' + b.name + '|' + (k + 1);
      const expDesc = DESC_OVERRIDES[oid] || clean(r.desc);
      const gotDesc = got.cells.J || '';
      if (gotDesc !== expDesc) fails.push({ check: 'desc_mismatch', anchor: t.prison + ' r' + rn, detail: 'got=' + JSON.stringify(gotDesc.slice(0, 80)) + ' exp=' + JSON.stringify(expDesc.slice(0, 80)) });
      const expZy = canonZy(r.zy);
      if ((got.cells.K || '') !== expZy) fails.push({ check: 'zy_mismatch', anchor: t.prison + ' r' + rn, detail: 'got=' + got.cells.K + ' exp=' + expZy });
      if ((got.cells.I || '') !== String(k + 1)) fails.push({ check: 'seq_mismatch', anchor: t.prison + ' r' + rn, detail: 'got=' + got.cells.I + ' exp=' + (k + 1) });
      if (!ALLOWED_L.has(got.cells.L || '')) fails.push({ check: 'L_illegal', anchor: t.prison + ' r' + rn, detail: 'L=' + got.cells.L });
      if (!ALLOWED_N.has(got.cells.N || '')) fails.push({ check: 'N_illegal', anchor: t.prison + ' r' + rn, detail: 'N=' + got.cells.N });
      if ((got.cells.P || '') !== '') fails.push({ check: 'P_notempty', anchor: t.prison + ' r' + rn, detail: 'P=' + got.cells.P });
      // attr cells on block start
      if (k === 0) {
        const a = b.attr;
        if (a) {
          if (!numEq(got.cells.E || '', a.area)) fails.push({ check: 'area_mismatch', anchor: t.prison + ' r' + rn, detail: 'E got=' + got.cells.E + ' attr=' + a.area });
          if (!numEq(got.cells.F || '', a.footprint)) fails.push({ check: 'foot_mismatch', anchor: t.prison + ' r' + rn, detail: 'F got=' + got.cells.F + ' attr=' + a.footprint });
          const boid = t.prison + '|' + b.name;
          const expD = (BUILDING_OVERRIDES[boid] && BUILDING_OVERRIDES[boid].D) || ((a.nowUse && a.nowUse.trim()) ? a.nowUse.trim() : (a.purpose || ''));
          if ((got.cells.D || '') !== expD) fails.push({ check: 'nowuse_mismatch', anchor: t.prison + ' r' + rn, detail: 'D got=' + got.cells.D + ' exp=' + expD });
          if ((got.cells.C || '') !== (a.purpose || '')) fails.push({ check: 'purpose_mismatch', anchor: t.prison + ' r' + rn, detail: 'C got=' + got.cells.C + ' exp=' + a.purpose });
          if (!numEq(got.cells.G || '', a.year)) fails.push({ check: 'year_mismatch', anchor: t.prison + ' r' + rn, detail: 'G got=' + got.cells.G + ' attr=' + a.year });
          if ((got.cells.H || '') !== (a.approval || '')) fails.push({ check: 'approval_mismatch', anchor: t.prison + ' r' + rn, detail: 'H got=' + got.cells.H + ' exp=' + a.approval });
        }
      }
      if (got.ht !== null && got.ht <= 0) fails.push({ check: 'ht_illegal', anchor: t.prison + ' r' + rn, detail: 'ht=' + got.ht });
    }
    // specialty non-decreasing per building
    const seq = b.rows.map(r => rankOf(r.zy));
    for (let i = 1; i < seq.length; i++) if (seq[i] < seq[i - 1]) fails.push({ check: 'zy_order', anchor: t.prison + ' ' + b.name + ' issue#' + (i + 1), detail: '专业序 ' + seq.join(',') });
  }
  const expTotal = expBuildings.reduce((a, b) => a + b.rows.length, 0);
  if (expTotal !== dataRows.length) fails.push({ check: 'row_total', anchor: t.prison + ' sheet', detail: '期望总行=' + expTotal + ' 成品行=' + dataRows.length });

  // c6 merges: no overlap & full coverage B..H per data row exactly one block; A4:Alast exists; header merges exist
  const cellSeen = new Map();
  for (const [c1l, r1, c2l, r2] of merges) {
    for (let rr = r1; rr <= r2; rr++) {
      const key = c1l + rr;
      if (cellSeen.has(key)) fails.push({ check: 'merge_overlap', anchor: t.prison + ' ' + key, detail: cellSeen.get(key) + ' vs ' + c1l + r1 + ':' + c2l + r2 });
      cellSeen.set(key, c1l + r1 + ':' + c2l + r2);
    }
  }
  const lastRn = 3 + expTotal;
  for (let rr = 4; rr <= lastRn; rr++) {
    for (const col of ['B', 'C', 'D', 'E', 'F', 'G', 'H']) {
      if (!cellSeen.has(col + rr)) fails.push({ check: 'merge_uncovered', anchor: t.prison + ' ' + col + rr, detail: '未在任何合并块内' });
    }
    if (!cellSeen.has('A' + rr)) fails.push({ check: 'merge_A_uncovered', anchor: t.prison + ' A' + rr, detail: 'A列未覆盖' });
  }
  for (const need of ['A1:P1', 'I2:P2', 'A2:A3', 'B2:B3', 'C2:C3', 'D2:D3', 'E2:E3', 'F2:F3', 'G2:G3', 'H2:H3']) {
    if (!merges.some(m => m[0] + m[1] + ':' + m[2] + m[3] === need)) fails.push({ check: 'header_merge_missing', anchor: t.prison, detail: need });
  }

  // c7 illegal chars in cells
  for (const r of dataRows) {
    for (const k of Object.keys(r.cells)) {
      const v = r.cells[k];
      if (/�|�/.test(v)) fails.push({ check: 'mojibake', anchor: t.prison + ' ' + k + r.rn, detail: v.slice(0, 40) });
    }
  }
  totalFails += fails.length;
  report.push({ prison: t.prison, expectedRows: expTotal, gotRows: dataRows.length, buildings: expBuildings.length, gotBlocks: gotBlocks.length, mergeCount: merges.length, fails });
}
console.log(JSON.stringify({ totalFails, report }, null, 1));
