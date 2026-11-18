# 派发待确认期间如何回查与重提分析

Type: grilling

归属 [FrameRead V1 模块与交付路线图](../map.md)

## Question

服务端返回 `ANALYSIS_DISPATCH_UNKNOWN` 后，同一受理代次仍有效，既无 broker 确认，也无持久消费领取。状态查询、SSE 初次订阅和用户再次提交同一作用域，各应返回什么可区分的业务状态或原因？Web 与扩展凭什么提示继续核对、接续原工作或在到期后允许用户显式重提？

用两个场景确认同一份契约。首次普通分析尚无报告。计划修订已有旧报告，提交后失去派发确认。两例都覆盖迟到确认或领取、首次领取期限届满，以及回查期间的用户重复操作。修订旧报告的持久保留、有效排队的显示优先级和执行开始时的重置沿用基线。

基线已定义持久阶段、202 条件、结果不明时的 5xx、过期与晚到处理，并保留既有五种公开状态及扩展诊断的空间。需要确认的是待确认窗口在公共 Interface 上的表达，以及两端如何据此操作。裁决后可冻结分析协调与 Web/扩展的这一段集成契约，并给 A3-16、A3-17 增加可判定的待确认用例。其他媒体和来源接口可独立推进。[SPEC §4.2](../../../docs/prototype/SPEC.md#spec-operations) · [§7.1](../../../docs/prototype/SPEC.md#spec-admission) · [§7.2](../../../docs/prototype/SPEC.md#spec-status) · [§8.1](../../../docs/prototype/SPEC.md#spec-api) · [ADR 0004](../../../docs/adr/0004-bound-video-task-admission.md)
