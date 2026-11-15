# Security boundaries

Use trusted, non-sensitive Python/pytest projects with prepared dependencies.

- The controller reads bounded text snapshots, filters unsafe paths and known secret patterns, and rejects symbolic links. Git input uses tracked files at a clean baseline. Checkout filters and private Git attributes require a separately validated profile.
- Only the controller writes accepted files, inside a private snapshot repository. The graph assigns phases and partners. Red adds tests while preserving existing test statements. Green and refactor preserve accepted tests. Bootstrap can append source scaffold and must leave an assertion failure.
- Provider CLIs receive explicit context and bounded schema requests in private temporary directories. Authentication follows the session's recorded mode. The adapters reject unexpected tool activity. Saved login stays with each provider CLI. [Transport details](providers.md)
- Docker runs project tests and demos as an unprivileged user with network disabled, read-only mounts and root filesystem, limited resources, and no passed provider credentials. The process supervisor bounds execution and output and cleans up owned containers.
- Session directories contain source, messages, and private evidence. Keep them out of published repositories. Optional tracing exports allowlisted metadata to local Langfuse. Keep the trace files and the local service keys private. [Tracing](tracing.md)

Secret-pattern checks cannot detect every credential. Candidate code and pytest share a process inside the container, so the test evidence assumes trusted toy projects. Controller checks cannot prove semantic correctness or assertion quality. Arbitrary host dependencies, hostile repositories, and automatic integration are outside this version's scope.
