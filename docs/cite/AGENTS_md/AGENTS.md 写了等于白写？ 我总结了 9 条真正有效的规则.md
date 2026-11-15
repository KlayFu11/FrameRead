---
title: "AGENTS.md 写了等于白写？ 我总结了 9 条真正有效的规则"
source: "https://mp.weixin.qq.com/s/_T_YF4-eQu4PvI_jj9hUuA"
author:
  - "[[UU]]"
published:
created: 2026-11-07
description: "AGENTS.md 不是项目百科，也不是越长越专业。它真正应该记录的，是 Codex 在这个项目里最容易犯的错误，以及它必须长期遵守、但无法从代码中稳定推断出来的约束。"
tags
---




# 文章内容

上一篇，我们聊了 Codex 的上下文管理。很多人看完之后，第一反应是：那我把项目介绍、技术栈和开发规范全部塞进 AGENTS.md，不就解决了吗？

我一开始也是这样做的。

项目背景、目录结构、Vue 版本、组件说明、编码规范、提交要求……一口气写了两百多行。看起来很完整，实际开发时，Codex 还是会乱改文件、重复造轮子，甚至在 Vue2 项目里写出 `<script setup>` 。

这篇文章的核心

我后来才明白： **AGENTS.md 不是项目百科，也不是越长越专业。它真正应该记录的，是 Codex 在这个项目里最容易犯的错误，以及它必须长期遵守、但无法从代码中稳定推断出来的约束。**

这篇不再讲概念。我直接把两个月使用后沉淀下来的 9 条规则拆开，并给出一份适合 Vue2、Vue3、Java 多技术栈项目的完整模板。

1PART 01

规则一：不要重复代码已经能告诉 Codex 的信息

很多 AGENTS.md 的第一屏，都是项目简介：这是一个 Vue2 项目，使用 Vuex、Element UI 和 Axios。

这类信息不是完全没用，但如果 `package.json` 、目录和现有代码已经写得很清楚，再写一遍，价值很低。Codex 自己读取项目就能知道。

✕ 无效写法

项目采用 Vue2、Vuex 和 Element UI。

请保持现有代码风格。

✓ 有效写法

这是 Vue2 项目，但禁止引入 Composition API、\<script setup> 和 Vue3 专用依赖。

状态管理继续使用现有 Vuex 模块，不新增 Pinia。

后者才有价值。因为“项目是 Vue2”通常可以被识别，但“公司项目禁止引入某种写法”无法仅靠扫描代码稳定判断。

📌 实战结论

判断一条信息是否值得写进去：删掉它以后，Codex 能否仅靠读取仓库得到同样准确的结论？能，就不必重复；不能，就应该保留。

✦ ✦ ✦

2PART 02

规则二：少写正确的废话，多写可验证的约束

“认真思考”“注意代码质量”“保持良好性能”，看起来都对，但几乎无法指导一次具体修改。

✕ 无效写法

请认真分析需求。

保持高质量代码。

注意性能和兼容性。

✓ 有效写法

修改前先定位现有调用链，不得根据文件名猜测真实入口。

禁止在循环中串行 await；确需串行时必须说明原因。

涉及 Android file:// 环境时，不得使用仅支持 http(s) 的资源加载方案。

有效规则应该能在代码审查时回答：这次到底遵守了没有？

💡 核心观点

一条无法检查、无法判断是否执行的规则，大概率只是在消耗上下文。

✦ ✦ ✦

3PART 03

规则三：优先记录“默认容易写错”的地方

AGENTS.md 最值钱的内容，不是“最佳实践大全”，而是项目里的反直觉约束。

例如我维护的项目里，有 Vue2、Vue3、Android WebView、iOS WebView，还有公司封装的请求层和原生交互层。模型按通用经验写代码，反而很容易错。

●●●AGENTS.md

\## 前端硬约束

\- Vue2 模块统一使用 Options API，禁止 \`\<script setup>\`。

\- 请求统一走项目的 fetchManager，不得新增 axios 实例。

\- 原生能力统一经过既有 bridge 封装，不得直接调用临时全局对象。

\- Android WebView 需要兼容 file:// 离线运行；引入资源前必须检查协议与相对路径。

\- iOS 地图页面禁止默认开启 3D、POI 等高内存能力。

这些规则并不“通用”，但恰恰因为不通用，才值得写。

🧭 优先级判断

AGENTS.md 不应该记录所有正确知识，而应该优先记录：Codex 按常规经验做时，最可能踩中的项目特殊坑。

✦ ✦ ✦

4PART 04

规则四：写清楚“先做什么”，但不要塞进完整工作流

有些长期动作可以放进 AGENTS.md，例如改代码前先读规范、涉及公共接口时先定位调用链、完成后必须跑哪些检查。

但不要把一个几十步的需求开发流程全部塞进根文件。那会让 AGENTS.md 又长又重，也会和不同任务的实际流程冲突。

✕ 无效写法

收到任何任务后，依次执行需求登记、需求存档、需求分析、用户确认、方案设计、边界确认、开发、评审、测试、提交……

✓ 有效写法

开始修改前：

1\. 阅读当前目录适用的 AGENTS.md。

2\. 定位真实调用链和现有实现。

3\. 先输出影响范围与实施计划；涉及跨模块或数据结构变更时，等待确认后再编码。

前者属于 Harness 或 Skill 要解决的问题；后者是所有开发任务都应遵守的基础约束。

⚠️ 注意

AGENTS.md 管长期默认规则；Skill 管某类任务的方法；Harness 管一件需求从开始到交付的完整流程。不要把三者全部揉进一个文件。

✦ ✦ ✦

5PART 05

规则五：多技术栈项目不要只放一个万能文件

我的项目里经常同时存在 Vue2、Vue3 和 Java。如果根目录只有一个巨大的 AGENTS.md，最后通常会出现两种结果：要么所有规则混在一起，要么为了避免冲突，规则写得特别空。

更合理的方式是分层：根目录只写全项目共同规则；技术栈或模块目录再写局部规则。Codex 会按当前工作目录和目标文件所在路径加载适用的指令，越靠近目标目录的规则越具体。

●●●目录结构

project/

├── AGENTS.md # 全项目共同规则

├── Codes/

│ ├── Frontend/

│ │ ├── AGENTS.md # 前端公共约束

│ │ ├── vue2-app/

│ │ │ └── AGENTS.md # Vue2 专属规则

│ │ └── vue3-app/

│ │ └── AGENTS.md # Vue3 专属规则

│ └── Backend/

│ └── AGENTS.md # Java/后端专属规则

└── docs/

这样修改 Vue2 页面时，不会同时把 Vue3 的 Pinia、Composition API 规则也塞进来；修改后端时，也不必读取一大段移动端 UI 规范。

📌 实战提醒

根文件管“全局共识”，子目录文件管“局部事实”。越具体的规则，越应该靠近它真正生效的代码。

✦ ✦ ✦

6PART 06

规则六：禁止事项必须同时给出正确出口

只写“禁止 axios”“禁止直接操作 DOM”，Codex 可能知道不能做，却不知道应该改用什么。结果就是它换一种同样不符合项目规范的写法。

✕ 无效写法

禁止新增 axios。

禁止直接调用原生能力。

✓ 有效写法

所有 HTTP 请求统一使用 \`@/core/fetchManager\`；找不到现有封装时先停止并说明缺口，不得自行新增请求库。

相册、定位、文件选择统一调用 \`nativeBridge\`；新增能力前先搜索既有 action 名称和参数格式。

每条禁止规则最好回答两个问题：为什么不能这样做？正确入口在哪里？

💡 实战结论

“不要做什么”只能阻止一次错误；“应该去哪里、使用什么”才能让 Codex 真正完成任务。

✦ ✦ ✦

7PART 07

规则七：把验证命令写成最小可执行清单

“修改后请测试”没有操作性。项目里可能有几十条命令，Codex 不知道跑哪个，也不知道哪些失败是历史问题。

●●●AGENTS.md

\## 完成前检查

\- 前端普通改动：\`npm run lint\`。

\- 涉及类型调整：额外执行 \`npm run type-check\`。

\- 涉及构建配置、依赖或公共组件：执行 \`npm run build\`。

\- 后端改动：执行对应模块单元测试，不要默认跑整个仓库。

\- 如果命令因环境缺失无法执行，必须明确列出：未执行项、原因、建议人工验证方式。

\- 不得用“理论上可行”代替验证结果。

这类规则能显著改善 Codex 最后的交付说明，也能避免它跑一个无关的大命令耗费时间。

⚠️ 注意

不要要求每次都执行所有测试。验证范围应与改动范围匹配，否则规则越严格，团队越容易绕过它。

✦ ✦ ✦

8PART 08

规则八：让 AGENTS.md 随错误演进，而不是一次写完

我现在不会专门抽一天“设计一份完美 AGENTS.md”。更有效的方式是：Codex 每犯一次具有复发可能的错误，就判断是否需要把纠正沉淀进去。

●●●给 Codex 的纠错指令

这次修改中，你错误地绕过了项目的 fetchManager，直接新增了 axios。

请完成两件事：

1\. 按现有请求封装重构本次代码；

2\. 在适用目录的 AGENTS.md 中补充一条简短、可执行的规则，避免同类问题再次发生。

不要记录本次需求细节，只记录可长期复用的项目约束。

这也是官方建议中非常实用的一点：当 Codex 对代码库作出错误假设时，修正它，并把可复用的修正沉淀到 AGENTS.md。

🧭 关键判断

真正成熟的 AGENTS.md，不是写出来的，而是在一次次真实开发和复盘中“长出来”的。

✦ ✦ ✦

9PART 09

规则九：定期删除，而不是只会追加

AGENTS.md 最常见的生命周期是：遇到问题就加一条，半年后变成几百行，里面同时存在过期规则、重复规则和互相冲突的规则。

我的做法是定期检查三类内容：

●●●清理清单

1\. 已经能从代码、配置或工具自动识别的说明 —— 删除。

2\. 只针对一次需求、一个临时事故的细节 —— 移到需求文档或删除。

3\. 已被 Skill、脚本、Lint、测试自动保证的规则 —— 在 AGENTS.md 中只保留入口，不重复展开。

官方最佳实践也强调：AGENTS.md 应保持短小、准确；文件开始膨胀时，把更详细的内容拆到独立文档或 Skills，只在主文件中保留索引和关键约束。

🛠️ 删除标准

AGENTS.md 的质量，不看写了多少，而看每一行是否仍然会改变 Codex 的行为。

✦ ✦ ✦

10PART 10

我现在使用的 AGENTS.md 模板

下面这份不是万能答案，但它比“项目介绍 + 技术栈 + 请认真思考”更接近真实工程。你可以先复制，再按项目删改。

●●●根目录模板

\# AGENTS.md

\## 1. 项目边界

\- 只修改本次需求直接涉及的文件，不顺手重构无关模块。

\- 不确定真实入口时，先搜索调用链，不得根据文件名猜测。

\- 涉及数据库结构、公共接口、公共组件或跨模块行为时，先输出影响范围并等待确认。

\## 2. 目录职责

\- \`Codes/Frontend/\`：前端工程；具体框架规则读取对应子目录 AGENTS.md。

\- \`Codes/Backend/\`：Java 后端工程。

\- \`docs/\`：需求、设计、测试和交付文档。

\- \`skills/\`：任务型专业能力；不要把 Skill 全文复制到本文件。

\## 3. 项目特殊约束

\- 优先复用项目现有组件、请求层和原生桥接层。

\- 找不到已有能力时先说明缺口，不得直接引入同类第三方库。

\- Android WebView 需要兼容 \`file://\` 离线运行。

\- 涉及用户数据、账号、定位、附件时，不在日志中输出敏感信息。

\## 4. 开发前

\- 阅读目标目录适用的 AGENTS.md 和相关规范。

\- 定位真实调用链、数据来源和现有测试。

\- 输出：涉及文件、修改原因、风险点、验证计划。

\## 5. 开发中

\- 保持最小改动，不修改与需求无关的格式和命名。

\- 不复制已有能力；新增公共代码前先搜索仓库。

\- 发现需求与现有实现冲突时停止猜测，明确列出冲突。

\## 6. 完成前

\- 检查 \`git diff\`，确认无无关改动、调试代码和敏感信息。

\- 执行与改动范围匹配的 lint、类型检查、测试或构建。

\- 无法执行的验证必须说明原因，禁止声称“已验证”。

\- 输出改动摘要、风险、已执行验证和待人工确认项。

\## 7. 禁止事项

\- 禁止绕过项目封装直接引入新请求库。

\- 禁止未经确认修改公共协议、数据库结构和跨项目公共资产。

\- 禁止为了让测试通过而删除断言、吞掉异常或扩大容错范围。

\- 禁止把本次需求细节长期写入 AGENTS.md。

✦ ✦ ✦

11PART 11

Vue2、Vue3 子目录应该怎么拆

根目录模板只写公共规则。框架差异下沉到各自目录，才不会互相污染。

●●●Vue2 局部规则

\# Codes/Frontend/vue2-app/AGENTS.md

\- 使用 Vue2 Options API，禁止 \`\<script setup>\` 和 Composition API。

\- 状态管理继续使用现有 Vuex 模块，不新增 Pinia。

\- 优先复用项目既有 mixin、filters 和公共组件。

\- 不得使用仅支持 Vue3 的组件 API。

\- 修改页面时检查 Android/iOS WebView 兼容性。

\- 请求统一使用现有 fetchManager，不创建独立 axios 实例。

●●●Vue3 局部规则

\# Codes/Frontend/vue3-app/AGENTS.md

\- 使用 Vue3 + TypeScript；新模块优先 Composition API 和 \`\<script setup>\`。

\- 状态管理使用现有 Pinia store，不新增平行状态源。

\- Props、Emits、接口返回值必须补充明确类型。

\- 优先使用项目已封装的 composables 与 UI 组件。

\- 不把 Vue2 mixin、filters 等旧模式复制到 Vue3 模块。

同一个仓库可以有多个 AGENTS.md。关键不是文件数量，而是规则作用域是否清楚。

✦ ✦ ✦

12PART 12

怎么验证它真的生效了

写完 AGENTS.md 后，不要直接用一个大需求验证。先做一次小范围“规则体检”。

●●●验证提示词

请先不要修改代码。

读取当前任务会生效的 AGENTS.md，并告诉我：

1\. 你读取到了哪些文件；

2\. 本目录最重要的 5 条约束；

3\. 如果要新增一个接口请求，必须使用哪个现有入口；

4\. 本项目有哪些明确禁止事项；

5\. 你准备执行哪些验证命令。

如规则之间存在冲突，请先指出，不要自行选择。

如果 Codex 回答不出来，通常不是模型不够聪明，而是规则位置不对、表达不够明确，或者文件已经长到重点被淹没。

📚 实战结论

先验证“是否读对规则”，再验证“是否写对代码”。这一步能省掉大量返工。

✦ ✦ ✦

13PART 13

最后：AGENTS.md 不是万能的

AGENTS.md 能解决的是长期、稳定、作用域明确的项目约束。它解决不了所有问题。

“如何设计一套 Vue2 页面”“如何做 Java API 开发”“如何完成一次数据库变更评审”，这些属于某类任务的专业方法，更适合放进 Skills。

“需求登记 → 分析 → 确认 → 设计 → 开发 → Review → 测试 → 提交”，这是完整交付流程，更适合由 Harness 串起来。

三者分工

AGENTS.md 告诉 Codex：在这个项目里，什么必须长期遵守。\
Skills 告诉 Codex：遇到某一类任务，应该怎么专业地完成。\
Harness 告诉 Codex：一件需求，从开始到交付，应该按什么顺序推进。

所以，我现在判断一条内容要不要放进 AGENTS.md，只问一句：

📚 经验总结

如果删掉这条规则，Codex 下一次是否还会在这个项目里犯同样的错误？\

会，就写进去。\
不会，就别让它占据上下文。

这也是我用了两个月之后，对 AGENTS.md 最真实的理解：

✅ 最终结论

它不负责介绍你的项目。\

它负责让 Codex 少在同一个地方摔第二次。



---

# 补充

## 指令写法（具体、可验证、祈使句）

1. **只写 Agent 从代码里猜不到的东西**：确切的 test/typecheck/lint 命令、代码里"看起来不用但其实在用"的目录、团队已定的错误处理器选型、部署方式、需要迁移评审的东西、任何你已经纠正过两次的规则。其余交给 Agent 自己读代码。 来源：https://anthropic.com/engineering/claude-code-best-practices

1. **用祈使句，不用"一般/通常/建议"**：写"用 pnpm 安装依赖"，不写"我们一般会使用 pnpm"。每多一个可商量的余地，遵循度就降一点。 来源：https://juejin.cn/post/7698623001063145487

1. **放真实命令，不放描述**：写 `pnpm test --run`，不写"运行测试套件"。前者可复制执行，后者需要模型自己翻译——翻译就会出错。 来源：https://juejin.cn/post/7698623001063145487

1. **每条规则要可判定**：判定标准只有一句——"能不能写个脚本一跑就知道过没过"。如"提交信息用 Conventional Commits"可判定；"提交信息要清晰"不可判定。 来源：https://juejin.cn/post/7698623001063145487

1. **Anthropic 的标杆例子**：写"Use 2-space indentation""API handlers live in src/api/handlers/"，优于"Format code properly""Keep files organized"。GitHub 指出：一个真实代码片段胜过三段风格描述。 来源：https://promptsrush.com/blog/how-to-write-agents-md-and-claude-md

1. **用强调词提升关键规则的遵循度**：`CRITICAL` / `IMPORTANT` / `MUST` / `ALWAYS` / `NEVER` 比"please try to avoid"有效；"Write clean code"这种无操作性的话直接删。 来源：https://zeeklog.com/jiao-cheng-claude-md-yu-agents-md-wan-quan-zhi-nan-rang-ai-bian-cheng-zhu-shou-geng-dong-ni-de-xiang-mu-12 ；https://aideck.website/articles/claude-md-agents-md-complete-guide

1. **好规则文件只回答三件事**：什么绝对不能做、做完跑什么验证、遇到不确定怎么停下问人。这三件清楚，文件就合格；项目技术栈每天变时，先写 5–8 条硬规则，不要先写完整版。 来源：https://radarai.top/articles/2026-年-ai-coding-agent-规则文件怎么写claudemdagentsmd-不是越长越好

1. **好的写法是"命令先于解释、显式约束、给反例、附命令速查"**；每条都问"删了它，Agent 会不会犯一个原本不会犯的错？"答否就删。 来源：https://clawpk.net:8443/tutorials/366-context-engineering-agents-md.html

------

## 5. 命令、验证与确定性闸门（Commands, Verification, Hooks）

1. **给 Agent 一个能产生 pass/fail 的检查**：测试、构建、lint、对比 fixture 的脚本、对比设计的截图。没有可跑的检查，Agent 只能以"看起来完了"为信号，你就是验证回路。 来源：https://anthropic.com/engineering/claude-code-best-practices

1. **非确定性指令 vs 确定性闸门**：CLAUDE.md、prompt、skill 属于"模型读后自己决定"的非确定性；hook、deny 规则、managed setting 属于"harness 必须执行"的确定性。必须永远发生或永不发生的规则，放进 hook，而不是靠措辞强硬。 来源：https://anthropic.com/engineering/claude-code-best-practices

1. **"Always typecheck before you finish" 这种句子大部分时候管用、不是每次都管用**；要确定性地强制，用 Stop hook 跑脚本，在通过前阻塞回合结束。 来源：https://anthropic.com/engineering/claude-code-best-practices

1. **Codex 的 AGENTS.md 规定**：如果文件里写了程序化校验，Agent **必须**在改完代码后跑完所有校验并尽力让它们通过，连文档改动也要跑。 来源：https://openai.com/so-DJ/index/introducing-codex/

1. **OpenAI 的工程实践：把 AGENTS.md 当"目录/地图"而非百科全书**，约 100 行，主要做指针，指向 `docs/` 下的系统记录（架构、设计文档、执行计划、技术债追踪），并用专用 linter 和 CI job 校验知识库新鲜、交叉链接、结构正确；一个"doc-gardening" Agent 定期扫过期文档并开修复 PR。 来源：https://openai.com/index/harness-engineering

1. **不要在 AGENTS.md 里写排版/风格检查规则**：让 Agent 用文字规则去检查又慢又费 token 还易错，交给 ESLint / Prettier，或用 Claude Code 的 hooks 在改完代码后自动触发。 来源：https://bolaslien.github.io/blog/2026/05/04/agents-md-writing-principles

1. **Code Review Rules 单独成节**：例如"任何读取请求输入却不做校验的 handler 一律标记""用字符串拼接拼 SQL 的标记掉"。Codex 的 GitHub 代码评审会读这一节，等于白送。 来源：https://explore.n1n.ai/blog/one-agents-md-to-rule-claude-code-cursor-and-codex-2026-10-13

------

## 6. 边界与禁止项（Always / Ask first / Never 三层）

1. **边界分层用 Always / Ask first / Never**：把模糊的"请注意"变成 Agent 可执行的决策。最常用、最有用的约束是"never commit secrets"。 来源：https://promptsrush.com/blog/how-to-write-agents-md-and-claude-md

1. **三层权限模型 allow / ask / deny**：安全可逆动作无需确认直接跑；高风险动作暂停等人审批；黑名单动作永不运行。Claude Code 在 `.claude/settings.json` 原生支持 deny；Cursor 用 per-rule ask/never 近似；AGENTS.md 只能用文字描述，无法强制。 来源：https://genalphai.com/agents-md-vs-claude-md

1. **把每个"never"从散文搬进强制**：凡是 Markdown 里"请不要"的措辞，都应进 `permissions.deny`（Claude Code）或 never 开关（Cursor）。散文边界只是文档，不是控制。 来源：https://genalphai.com/agents-md-vs-claude-md

1. **"熔断器"思路**：写死不能碰的路径（如 `src/gen/` 生成代码、某个 legacy 目录）、不能装的包、不能改的生产配置。比反复口头解释便宜。 来源：https://github.com/Zenty-Me/agent-dev-kit/blob/main/agents-learning/project-instructions.md

1. **n1n.ai 的硬规则范例**：禁止提交 `.env*`/`.pem`/`*.key`；非显式要求不跑 `git push`、`git reset --hard`、`git clean -fd`、force-push、破坏性 DB 命令；不"修复"失败测试（不放松断言、不加 `.skip`）。 来源：https://explore.n1n.ai/blog/one-agents-md-to-rule-claude-code-cursor-and-codex-2026-10-13

------

## 7. 分层与嵌套（Layering & Nesting）

1. **层级**：个人全局（`~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`）→ 仓库根 → 子目录 override；越近越优先。monorepo 每子包放一个嵌套 `AGENTS.md`，只有在该处工作时才加载，零成本。 来源：https://promptsrush.com/blog/how-to-write-agents-md-and-claude-md

1. **就近原则**：用户在聊天中的直接提示词（最高）> 距离编辑文件最近的 AGENTS.md > 根 AGENTS.md。OpenAI 主仓库在撰写时存在 88 个 AGENTS.md；社区估计已有 60,000+ 开源仓库采用。 来源：http://agents.md/ ；https://dnt.co.il/agents-md-vs-claude-md-where-agent-context-actually-lives

1. **路径作用域规则**：Claude Code 用 `.claude/rules/` 配 `paths:` frontmatter，只在匹配文件时加载（如 `paths: ["src/api/**/*.ts"]`）；Cursor 用带 globs 的 `.mdc` 文件（注意：`.cursor/rules/` 里普通 `.md` 会被忽略，必须是 `.mdc`）。 来源：https://promptsrush.com/blog/how-to-write-agents-md-and-claude-md ；https://explore.n1n.ai/blog/one-agents-md-to-rule-claude-code-cursor-and-codex-2026-10-13

1. **Codex 的注入顺序**：`AGENTS.override.md` → `AGENTS.md` → `config.toml` 的 `developer_instructions`，且 `AGENTS.override.md` 与 `AGENTS.md` 从 Git 根到 cwd 逐级向上收集，受 32 KiB 默认上限约束。 来源：https://openai.com/index/unrolling-the-codex-agent-loop/

1. **monorepo 嵌套范例**：`packages/web/AGENTS.md`（前端规则）、`packages/api/AGENTS.md`（后端规则）、`packages/shared/AGENTS.md`（库开发规则），编辑 `packages/web/src/` 时优先读 web 的规则再回落到根。 来源：https://zeeklog.com/jiao-cheng-claude-md-yu-agents-md-wan-quan-zhi-nan-rang-ai-bian-cheng-zhu-shou-geng-dong-ni-de-xiang-mu-9

------

## 8. 渐进式披露：Skills / Hooks / 多文件拆分

1. **团队流程放进 skill**：发布流程、事故 runbook、API 文档写法这类"Agent 不知道但能学会"的知识，存到 `.claude/skills/<name>/SKILL.md`。带副作用的流程加 `disable-model-invocation: true`，只有你 `/release` 时才跑。skill 比 CLAUDE.md 更轻量，长流程不污染无关 bug fix 的上下文。 来源：https://anthropic.com/engineering/claude-code-best-practices

1. **多步骤程序（发布检查单、迁移 runbook）不该常驻加载**，移到 skill；多步骤部署流程同理。Anthropic 明确建议把偶发知识做进 skill。 来源：https://promptsrush.com/blog/how-to-write-agents-md-and-claude-md

1. **OpenAI 的 progressive disclosure 工程化**：Agent 从小的稳定入口出发，被教会"下一步去哪找"，而不是一上来被淹没。并用"enforce mechanically"（专用 linter + CI）保证知识库的新鲜与交叉引用。 来源：https://openai.com/index/harness-engineering

1. **khasky/awesome-agents-md 的做法**：单一自包含 AGENTS.md + `rules/` 多领域文件（frontend-design、git-hooks、i18n、incident-response、payments、security 等），且"hooks 优于 prose"——把规则下沉为可执行的 hook 而非描述性文字。 来源：https://github.com/khasky/awesome-agents-md

------

## 9. 维护与防腐烂（Maintenance & Anti-Rot）

1. **指令文件会腐烂**：测试命令变了，文件还写着旧的，每个 Agent 头两轮都在重新发现。把文件当代码，构建流程一变就在 PR 里顺手改它。 来源：https://auravcs.com/learn/agents-md-vs-claude-md

1. **事后蒸馏，不要开工前拍脑袋写空话**：先手工干几遍，把返工纠偏记成规则；"第二次犯错即写入规则"。直接 `/init` 生成的文件大多是项目架构、可查信息、重复描述，占着 context 的废话，应作为草稿再自改。 来源：https://github.com/Zenty-Me/agent-dev-kit/blob/main/agents-learning/project-instructions.md ；https://bolaslien.github.io/blog/2026/05/04/agents-md-writing-principles

1. **一条已经不成立的规则比没有规则更糟**：它会带着 Agent 稳定地走错。改了构建流程、加了新目录，就在同一 PR 里改它；把规则文件纳入 Code Review 流程，和代码一起迭代。 来源：https://juejin.cn/post/7698623001063145487 ；https://radarai.top/articles/2026-年-ai-coding-agent-规则文件怎么写

1. **定期体检工具**：Claude 的 `/doctor prompt-audit` 会标出为旧模型写的保姆式约束（MUST/NEVER 堆砌、think carefully）、指向已不存在文件或自相矛盾的指令；`/context` 或 `/memory` 可确认文件是否被加载；换模型后跑一遍清理遗留约束。 来源：https://anthropic.com/engineering/claude-code-best-practices ；https://github.com/Zenty-Me/agent-dev-kit/blob/main/agents-learning/project-instructions.md

1. **awesome-agents-md 的 `amd` CLI**：提供 init 生成 + check 体检（检测密钥泄露与整体转发，整体转发判 FAIL），零依赖，可作为仓库级守门。 来源：https://github.com/YuanyuanMa03/awesome-agents-md

1. **外部化多会话状态**：用 `feature_list.json` 和 append-only 的进度日志，消除"新会话自信地重做/撤销昨天工作"这一多会话 Agent 最大失败模式。状态存文件而非聊天历史——文件能跨会话/模型、进 git、可共享；聊天历史无结构、token 无界、随增长退化（Chroma 的 context-rot 研究在 18 个前沿模型上记录过）。 来源：https://genalphai.com/agents-md-vs-claude-md
