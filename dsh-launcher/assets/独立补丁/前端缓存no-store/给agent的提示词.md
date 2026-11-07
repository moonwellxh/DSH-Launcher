# 给 agent 的提示词（前端缓存 no-store 补丁）

> 用途：将来需要重新启用这个补丁时，把下面整段复制给一个 agent。
> 它会先查证再动手，不会直接覆盖你的文件。

---

```
【独立补丁 · 前端缓存 no-store】请按以下要求处理，先出方案，我认可后再动手。

背景
这个补丁原本挂在 dsh-launcher 的自动装载清单里，2026-11-06 已独立出来，脱离自动流程。
它解决的是：DSH 升级或重建前端后，浏览器复用旧 index.html 导致白屏、
或控制台报 client-modules: boot manifest batches must be an array。
补丁只覆盖构建产物 @deepseek-ai\dsh-host-frontend-static\lib\index.js，三档缓存策略：
index.html 用 no-store、带内容哈希的资源用 immutable、其余用 no-cache + ETag/304。

位置
%USERPROFILE%\.agents\skills\dsh-launcher\assets\独立补丁\前端缓存no-store\
内含：操作指南.md、载荷文件\...\lib\index.js、安装与还原脚本（参考实现）、
源码增量 patch、补丁引擎-公共库.ps1（自包含副本）。

要求
1. 先读同目录的 操作指南.md，并核实三件事：
   a 当前 DSH 版本与前端构建产物路径；
   b 现网是否真的存在"不硬刷新就复现"的缓存问题（给出复现与不复现的对照）；
   c 当前版本上游是否已经修掉。
   三条有任何一条不成立，就停下来告诉我"不需要装"，不要动文件。
2. 若确实需要：载荷极可能已过版本（现载荷对应 0.2.1-rc.2）。
   按 操作指南.md 第五节用源码增量 patch 在源码树重建载荷，构建后取 lib/index.js 覆盖载荷文件；
   重建完必须把源码树 git checkout 还原干净，不许把增量留在工作树里。
3. 安装前：秒级时间戳备份目标文件、写回滚命令、把改动记进 %DSH_HOME%\AGENTS-changelog.md。
4. 安装后：重启 dsh web，跑 assets\tools\test-frontend-cache.mjs 验证
   （期望 index no-store / 哈希资源 immutable / 普通资源 no-cache+ETag 且条件请求 304）。
   浏览器还要 Ctrl+F5 硬刷新一次。
5. 全过程产物（临时脚本、构建日志、验证输出）统一放在
   D:\DSHS\升级\<你新建的目录>\ 下，不要散落到工作区根。

硬约束
- 不覆盖 TS 源码，只覆盖构建产物。
- 版本对不上不硬装。
- 失败按回滚命令还原；还原后重启 dsh web 并说明失败原因。
- 未经我确认，不要开始第 2 步之后的任何写操作。
```
