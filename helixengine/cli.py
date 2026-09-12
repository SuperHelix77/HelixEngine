"""Command line entrypoint for explicit local Helix Engine operations."""

import argparse
import json
import sys
from pathlib import Path

from .runtime import Runtime, jsonable_memory
from .server import serve


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _read_json(path):
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _reference(value):
    path = Path(value).expanduser()
    if path.is_file():
        return _read_json(path)
    return json.loads(value)


def _parser():
    parser = argparse.ArgumentParser(prog="helixengine")
    parser.add_argument("--data-dir", default="~/.helixengine")
    commands = parser.add_subparsers(dest="command", required=True)

    serve_command = commands.add_parser("serve", help="serve the loopback release console")
    serve_command.add_argument("--port", type=int, default=8769)
    serve_command.add_argument("--open", action="store_true")

    for name in ("on", "off", "status", "doctor"):
        commands.add_parser(name)

    run = commands.add_parser("run", help="execute one argv exactly once")
    run.add_argument("--kind", choices=("generic", "pytest", "compiler"), default="generic")
    run.add_argument("--cwd", default=None)
    run.add_argument("--timeout", type=float, default=None)
    run.add_argument("--json", action="store_true", dest="json_output", help="emit a result envelope")
    run.add_argument("command_argv", nargs=argparse.REMAINDER, metavar="COMMAND")

    retrieve = commands.add_parser("retrieve", help="retrieve exact retained command output")
    retrieve.add_argument("receipt")
    retrieve.add_argument("--stream", choices=("stdout", "stderr"), required=True)
    retrieve.add_argument("--start", type=int)
    retrieve.add_argument("--end", type=int)

    usage = commands.add_parser("usage-import", help="explicitly import native counters from a JSON receipt")
    usage.add_argument("run_id")
    usage.add_argument("receipt_json")

    memory = commands.add_parser("memory", help="operate on exact project-scoped memory records")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    record = memory_commands.add_parser("record")
    record.add_argument("project")
    record.add_argument("session")
    record.add_argument("event_id")
    record.add_argument("--file", default="-", help="exact bytes to record; '-' reads stdin")
    search = memory_commands.add_parser("search")
    search.add_argument("project")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    timeline = memory_commands.add_parser("timeline")
    timeline.add_argument("project")
    timeline.add_argument("session")
    timeline.add_argument("--after", type=int, default=0)
    timeline.add_argument("--limit", type=int, default=50)
    retrieve_memory = memory_commands.add_parser("retrieve")
    retrieve_memory.add_argument("project")
    retrieve_memory.add_argument("record_hashes", nargs="+")
    retrieve_memory.add_argument("--max-bytes", type=int, default=1048576)
    replay = memory_commands.add_parser("replay")
    replay.add_argument("project")
    replay.add_argument("session")
    replay.add_argument("--after", type=int, default=0)
    replay.add_argument("--limit", type=int, default=50)
    replay.add_argument("--max-bytes", type=int, default=1048576)

    plan = commands.add_parser("plan", help="explicitly register or invoke a checked named plan")
    plan_commands = plan.add_subparsers(dest="plan_command", required=True)
    register = plan_commands.add_parser("register")
    register.add_argument("spec")
    execute_spec = plan_commands.add_parser("execute-spec")
    execute_spec.add_argument("spec")
    execute_spec.add_argument("--timeout", type=float)
    run_plan = plan_commands.add_parser("run")
    run_plan.add_argument("reference")
    run_plan.add_argument("--timeout", type=float)
    rebind = plan_commands.add_parser("rebind-inputs")
    rebind.add_argument("reference")
    rebind.add_argument("new_version", type=int)
    receipt = plan_commands.add_parser("receipt")
    receipt.add_argument("sha256")
    return parser


def _write_exact(stream, raw):
    if not raw:
        return
    buffer = getattr(stream, "buffer", stream)
    buffer.write(raw)
    try:
        buffer.flush()
    except AttributeError:
        pass


def _exit_code(result):
    code = result.get("exit_code")
    if result.get("timed_out"):
        return 124
    if result.get("interrupted"):
        return 130
    if code is None:
        return 1
    return 128 + abs(code) if code < 0 else code


def main(argv=None):
    args = _parser().parse_args(argv)
    runtime = Runtime(args.data_dir)
    try:
        if args.command == "serve":
            serve(runtime, args.port, args.open)
            return 0
        if args.command == "status":
            print(_json(runtime.settings()))
            return 0
        if args.command in ("on", "off"):
            current = runtime.settings()
            result = runtime.switch(args.command == "on", current["revision"])
            print(_json(result))
            return 0
        if args.command == "doctor":
            result = runtime.state.doctor()
            print(_json(result))
            return 0 if result["ok"] else 1
        if args.command == "run":
            command_argv = list(args.command_argv)
            if command_argv[:1] == ["--"]:
                command_argv = command_argv[1:]
            if not command_argv:
                raise ValueError("A command argv is required after --")
            result = runtime.run(command_argv, args.cwd, kind=args.kind, timeout=args.timeout)
            if args.json_output:
                print(
                    _json(
                        {
                            "run": result["run"],
                            "receipt": result["receipt"],
                            "packet_receipt": result["packet_receipt"],
                        }
                    )
                )
            else:
                # No CLI logging is added to native streams.  The receipt is
                # retained in status/SQLite and can be retrieved explicitly.
                _write_exact(sys.stdout, result["stdout"])
                _write_exact(sys.stderr, result["stderr"])
            return _exit_code(result)
        if args.command == "retrieve":
            print(_json(runtime.retrieve(args.receipt, args.stream, args.start, args.end)))
            return 0
        if args.command == "usage-import":
            print(_json(runtime.usage_import(args.run_id, args.receipt_json)))
            return 0
        if args.command == "memory":
            if args.memory_command == "record":
                raw = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).expanduser().read_bytes()
                print(_json(runtime.memory_record(args.project, args.session, args.event_id, raw)))
            elif args.memory_command == "search":
                print(_json(jsonable_memory(runtime.memory_search(args.project, args.query, args.limit))))
            elif args.memory_command == "timeline":
                print(_json(jsonable_memory(runtime.memory_timeline(args.project, args.session, args.after, args.limit))))
            elif args.memory_command == "retrieve":
                print(_json(jsonable_memory(runtime.memory_retrieve(args.project, args.record_hashes, args.max_bytes))))
            elif args.memory_command == "replay":
                print(_json(jsonable_memory(runtime.memory_replay(args.project, args.session, args.after, args.limit, args.max_bytes))))
            return 0
        if args.command == "plan":
            if args.plan_command == "register":
                print(_json(runtime.plan_register(_read_json(args.spec))))
            elif args.plan_command == "execute-spec":
                reference = runtime.plan_register(_read_json(args.spec))
                print(_json(jsonable_memory(runtime.plan_run(reference, args.timeout))))
            elif args.plan_command == "run":
                print(_json(jsonable_memory(runtime.plan_run(_reference(args.reference), args.timeout))))
            elif args.plan_command == "rebind-inputs":
                print(_json(runtime.plan_rebind(_reference(args.reference), args.new_version)))
            elif args.plan_command == "receipt":
                print(_json(runtime.store.receipt(args.sha256)))
            return 0
        raise ValueError("Unknown command")
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"helixengine: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
