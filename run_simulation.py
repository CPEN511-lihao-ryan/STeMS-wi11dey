#!/usr/bin/env python3
"""
ChampSim Prefetching Simulation Runner
Ryan Meshulam and Lihao Xue, 2024
---

Runs a ChampSim simulation and saves the results.
"""
import argparse
import json
import pathlib
import subprocess
import datetime
import uuid
from shutil import copyfile, rmtree
from typing import List

default_output_dir = "simulation-results"


def parse_arguments():
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Run a ChampSim simulation and save the results"
    )
    parser.add_argument(
        "--config",
        "-c",
        metavar="champsim_config.json",
        default="champsim_config.json",
        nargs="?",
        dest="config",
        help="Configuration file to pass to ChampSim.",
    )
    """parser.add_argument(
        "--daemonize",
        "-d",
        action="store_true",
        dest="daemonize",
        help="Daemonize ChampSim and return immediately, or keep ChampSim running in the foreground. Will print the PID of the running process.",
    )"""
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        dest="quiet",
        help="Print less output to the console.",
    )
    parser.add_argument(
        "--skip-make",
        required=False,
        action="store_true",
        dest="skip_make",
        help="Skip the make process. Useful if you've already built and configured ChampSim for this configuration.",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="output_dir",
        default=default_output_dir,
        nargs="?",
        dest="output",
        help="Output directory to save the results.",
    )
    parser.add_argument(
        "--warmup-instructions",
        "-w",
        metavar="instructions",
        default=50000000,
        type=int,
        dest="warmup",
        help="The number of instructions in the warmup phase.",
    )
    parser.add_argument(
        "--simulation-instructions",
        "-s",
        metavar="instructions",
        default=200000000,
        type=int,
        dest="sim",
        help="The number of instructions in the warmup phase.",
    )
    parser.add_argument(
        "--trace",
        metavar="trace",
        action="append",
        required=False,
        help="Trace file to run. Cannot be used concurrently with --tracelist.",
    )
    parser.add_argument(
        "--tracelist",
        metavar="list_file.txt",
        required=False,
        help="File containing a list of trace files to run. Cannot be used concurrently with --trace. Recommended to run with --daemonize.",
    )

    args = parser.parse_args()
    if ((args.trace is None) and (args.tracelist is None)) or (
        (args.trace is not None) and (args.tracelist is not None)
    ):
        parser.error("Exactly one of --trace or --tracelist must be specified.")

    return args


def create_directory(
    output_dir: pathlib.Path, trace_path: pathlib.Path, prefetcher: str, dry_run=False
):
    # Create output directory
    if not output_dir.exists():
        output_dir.mkdir()

    # Get current datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.isoformat(timespec="seconds").replace(":", "").replace("+0000", "Z")

    trace_name = trace_path.stem

    # Construct results directory
    results_dir = now_str + "_" + trace_name + "_" + prefetcher
    results_path = output_dir / results_dir
    if (not results_path.exists()) and (not dry_run):
        results_path.mkdir()
    return results_path


def run_simulation(
    trace_path: List[pathlib.Path],
    config_path: pathlib.Path,
    output_dir: pathlib.Path,
    prefetcher: str,
    warmup_instructions: int,
    simulation_instructions: int,
    run_id: str,
    daemonize: bool = True,
    quiet: bool = False,
):
    # Create output directory
    results_path = create_directory(
        output_dir=output_dir, trace_path=trace_path[0], prefetcher=prefetcher
    )

    if not quiet:
        print(
            "Running simulation and depositing results at "
            + str(results_path.absolute().resolve())
        )

    # Copy config file over
    copyfile(config_path, results_path / "champsim_config.json")

    # Generate run command
    cmd = [
        str(pathlib.Path("bin/champsim").resolve()),
        "--warmup-instructions",
        str(warmup_instructions),
        "--simulation-instructions",
        str(simulation_instructions),
        "--json",
        str((results_path / "simulation_results.json").resolve()),
        # " >> ",
        # str((results_path / "sim_output.log").resolve()),
    ]

    # Add the trace files to the command
    for trace in trace_path:
        cmd.append(str(trace.resolve()))

    if not quiet:
        print("Command: " + str(cmd))

    # Compute checksum of the trace files
    trace_checksums: List[str] = []
    for trace in trace_path:
        trace_checksums.append(
            subprocess.run(
                ["sha1sum", str(trace)], capture_output=True, text=True, check=True
            ).stdout.strip()
        )

    # Compute checksum of the configuration file
    config_checksum = subprocess.run(
        ["sha256sum", str(config_path)], capture_output=True, text=True, check=True
    ).stdout.strip()

    # Get current git commit
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    # Save the run metadata to a file
    with open(results_path / "run_metadata.json", "w") as f:
        json.dump(
            {
                "trace_path": [str(trace) for trace in trace_path],
                "trace_checksum": trace_checksums,
                "git_commit": git_commit,
                "prefetcher": prefetcher,
                "run_id": run_id,
                "sim_id": uuid.uuid4().hex,
                "run_datetime": datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "command": str(cmd),
            },
            f,
        )

    # Run the simulation

    with open(results_path / "sim_output.log", "wb") as sim_output_file:
        if daemonize:
            # Run in the background
            sim_process = subprocess.Popen(
                cmd, stdout=sim_output_file, stderr=subprocess.STDOUT, text=True
            )
            if not quiet:
                print(
                    "ChampSim running in the background with PID "
                    + str(sim_process.pid)
                )
            else:
                print("PID: " + str(sim_process.pid))
            return
        else:
            # Does not work right now!
            # Run in the foreground
            """
            sim_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr_file, text=True)
            if not quiet:
                for line in iter(sim_process.stdout.readline, ''):
                    print(line, end='')
                    stdout_file.write(line)"""
            return


def main():
    args = parse_arguments()
    # print(args)

    # tracelist is a list of lists of traces, where each list of traces should
    # be the same length and should correspond to the number of cores, or one
    if args.tracelist is not None:
        # Determine if we're running multiple tests or just one
        with open(args.tracelist, "r") as f:
            tracelines = f.read().splitlines()
        tracelist: List[List[str]] = [
            traceline.strip(", \n").split(",") for traceline in tracelines
        ]
        for trace in tracelist:
            if len(trace) != len(tracelist[0]):
                raise ValueError(
                    "Each line in the tracelist file must have the same number of traces."
                )
    else:
        tracelist: List[List[str]] = args.trace

    tracepaths = [[pathlib.Path(trace) for trace in traces] for traces in tracelist]
    # print(tracepaths)

    # Generate a unique ID for this run
    run_id: str = uuid.uuid4().hex

    # Save the configuration file in a temporary folder
    temp_path = pathlib.Path("temp_" + run_id)
    if not temp_path.exists():
        temp_path.mkdir()
    else:
        raise FileExistsError(
            "Temporary directory already exists! This should not occur since we're using UUIDs. Exiting!"
        )
    config_path = temp_path / "champsim_config.json"
    copyfile(args.config, config_path)

    # Parse the configuration file
    with open(config_path, "r") as f:
        config_parsed = json.load(f)

    l1d_prefetcher = config_parsed["L1D"]["prefetcher"]
    l2c_prefetcher = config_parsed["L2C"]["prefetcher"]

    prefetcher = l1d_prefetcher if l1d_prefetcher != "no" else l2c_prefetcher
    num_cores = int(config_parsed["num_cores"])
    
    # Validate that the number of traces is equal to the number of cores or one
    if (len(tracepaths[0]) != 1 and len(tracepaths[0]) != num_cores):
        raise ValueError(
            "The number of traces must be equal to the number of cores or one."
        )
    
    # If the number of traces is one, then we need to duplicate the trace for each core
    if (len(tracepaths[0]) == 1 and num_cores > 1):
        for i in range(len(tracepaths)):
            for j in range(num_cores - 1):
                tracepaths[i].append(tracepaths[i][0])
    
    # print(tracepaths)

    output_dir = pathlib.Path(args.output)

    # Configure and make ChampSim
    if not args.skip_make:
        configure_process = subprocess.run(
            ["./config.sh", str(config_path.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        if not (args.quiet):
            print("ChampSim configured. Printing STDOUT of ./config.sh")
            print(configure_process.stdout)
            print("\nPrinting STDERR of ./config.sh")
            print(configure_process.stderr)
            print("\n")

        make_process = subprocess.run(
            ["make", "-j", "28"], capture_output=True, text=True, check=True
        )
        if not (args.quiet):
            print("ChampSim built. Printing STDOUT of make")
            print(make_process.stdout)
            print("\nPrinting STDERR of make")
            print(make_process.stderr)
            print("\n")

    # Run the simulations
    for tracepath in tracepaths:
        run_simulation(
            trace_path=tracepath,
            config_path=config_path,
            output_dir=output_dir,
            prefetcher=prefetcher,
            run_id=run_id,
            warmup_instructions=args.warmup,
            simulation_instructions=args.sim,
        )

    rmtree(temp_path)


if __name__ == "__main__":
    main()
