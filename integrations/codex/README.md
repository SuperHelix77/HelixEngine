# Helix Context in Codex

Install Helix Engine first using the repository's installation guide. Start the HUD with the desktop launcher. The Engine and Codex remain separate processes; the HUD observes commands explicitly routed through the Engine.

This directory contains the optional [Helix Context skill](skills/helixcontext/SKILL.md). Add its `helixcontext` folder to your project's `.agents/skills/` directory, or attach the file directly to a Codex task. If you already have a customized Helix Context skill, review and merge the command-routing instructions instead of overwriting it. See the [official skill documentation](https://developers.openai.com/codex/skills/) for your installed Codex version's discovery controls.

An initial task message can be:

> Use the attached Helix Context skill. Helix Engine is installed in my home directory's `.helixengine-venv`. Use its Python executable with `-m helixengine`. Retain my normal final answers, effort and tools. Route suitable foreground commands through it and retrieve exact evidence whenever a packet is insufficient.

For a direct terminal smoke test on macOS/Linux:

```sh
"$HOME/.helixengine-venv/bin/python" -m helixengine run -- python3 -c 'print("Helix routed command")'
```

On Windows PowerShell:

```powershell
& "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m helixengine run -- py -c 'print("Helix routed command")'
```

The run appears in the local HUD. Native token counters require explicit usage receipt imports; routing a command does not reveal Codex's hidden context or billing formula. This release does not install pre-inference hooks, change Codex's base instructions, lower reasoning effort, rewrite final answers, or claim general model parity. A future caller integration can use the same Engine interfaces without changing this boundary.
