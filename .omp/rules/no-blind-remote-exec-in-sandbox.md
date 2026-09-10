---
name: no-blind-remote-exec-in-sandbox
description: "Before instructing/attempting to hit a remote host or claiming a live command's result, verify tool execution actually happens in the user's environment, not an unreachable sandbox"
condition: ["curl.*10\\.\\d+\\.\\d+\\.\\d+", "Testing reachability of Jenkins host"]
scope: ["tool:bash(*)", "text"]
---

This session's shell is a sandbox with no network path to the user's internal infrastructure (internal IPs, their Jenkins host, their cache dirs, their conf files). Before running diagnostic commands against a host the user mentioned, first check whether that host/file is actually reachable/present *in this environment* (e.g. a quick existence/reachability check) rather than assuming shared execution context with the user's shell. If the check shows no access (missing conf, missing cache dir, connection timeout), say so immediately and stop trying more commands aimed at their infra — instead give the user exact commands to run themselves, and stop presenting your own unreachable-sandbox attempts as if they were validating the user's environment.