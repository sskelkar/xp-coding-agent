# Pair runtime roadmap

The existing product runs two continuing XP partners through a controller-owned LangGraph. It supports outcome confirmation, business questions, red/green/refactor, role rotation, executed demos, private snapshot delivery, and resumption at business interrupts. Scripted production runs exercise the same graph, runner, and workspace code as live sessions. [Current runtime](pair-runtime.md)

- **Live-provider qualification.** Run repeatable synthetic tasks with authorized accounts, record model and auth mode, and distinguish passing code from retained context and successful business feedback.
- **Business feedback after a demo.** Qualify sessions where the desired behavior changes and accepted tests need deliberate revision. Currently those tests remain frozen during green and refactor.
- **Recovery.** Extend restart tests beyond waiting business boundaries. An interruption during a hosted request can repeat that call.
- **Broader project profiles.** Qualify dependency preparation and larger snapshots individually while keeping one controller writer and isolated execution.

[Recorded validation](evaluation.md) · [Evaluation methods](pair-evaluations.md)
