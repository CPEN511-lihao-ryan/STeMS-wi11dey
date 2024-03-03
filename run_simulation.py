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
import re

default_output_dir = "simulation-results"


def parse_arguments():
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Run a ChampSim simulation and save the results"
    )
    parser.add_argument(
        "--predictor",
        required=False,
        metavar="branch_predictor",
        default="hashed_perceptron",
        help="Branch predictor to use."
    )
    parser.add_argument(
        "--l1d",
        metavar="l1d_prefetcher",
        required=False,
        default="no",
        help="L1D prefetcher to use."
    )
    parser.add_argument(
        "--l2c",
        metavar="l2c_prefetcher",
        required=False,
        default="no",
        help="L2C prefetcher to use."
    )
    parser.add_argument(
        "--llc-replacement",
        metavar="llc_replacement",
        required=False,
        default="lru",
        help="LLC replacement policy to use."
    )
    parser.add_argument(
        "--cores",
        metavar="num_cores",
        required=False,
        type=int,
        default=1
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
        "--force-build",
        required=False,
        action="store_true",
        dest="force_build",
        help="Force rebuilding the simulator, even if there already exists a binary for it.",
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
    output_dir: pathlib.Path, trace_num: int, instr_offset: int, binary_name: str, dry_run=False
):
    # Create output directory
    if not output_dir.exists():
        output_dir.mkdir()

    # Get current datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.isoformat(timespec="seconds").replace(":", "").replace("+0000", "Z")

    # Construct results directory
    results_dir = now_str + "_" + binary_name + "_" + str(trace_num) + "-" + str(instr_offset)
    results_path = output_dir / results_dir
    if (not results_path.exists()) and (not dry_run):
        results_path.mkdir()
    return results_path


def run_simulation(
    trace_path: List[pathlib.Path],
    output_dir: pathlib.Path,
    binary_name: str,
    run_id: str,
    daemonize: bool = True,
    quiet: bool = False,
):
    first_trace_filename = trace_path[0].name
    first_trace_num = int(re.match(r"^\d{3}", first_trace_filename).group(0))
    first_trace_instr_offset = int(re.search(r"(?<=-)\d+(?=B\.champsimtrace)", first_trace_filename).group(0))

    # Create output directory
    results_path = create_directory(
        output_dir=output_dir, trace_num=first_trace_num, instr_offset=first_trace_instr_offset, binary_name=binary_name)

    if not quiet:
        print(
            "Running simulation and depositing results at "
            + str(results_path.absolute().resolve())
        )

    # Generate run command
    cmd = [
        str((pathlib.Path("bin")/binary_name).resolve())
    ]

    # Add the trace files to the command
    for trace in trace_path:
        cmd.append("-traces")
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
                "binary_name": binary_name,
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
        tracelist: List[List[str]] = [args.trace]

    tracepaths = [[pathlib.Path(trace) for trace in traces] for traces in tracelist]
    # print(tracepaths)

    # Generate a unique ID for this run
    run_id: str = uuid.uuid4().hex

    binary_name = args.predictor + "-" + args.l1d + "-" + args.l2c + "-" + args.llc_replacement + "-" + str(args.cores) + "core"
    
    # Validate that the number of traces is equal to the number of cores or one
    if (len(tracepaths[0]) != 1 and len(tracepaths[0]) != args.cores):
        print("len(tracepaths): ", str(len(tracepaths)))
        print(tracepaths)
        raise ValueError(
            "The number of traces must be equal to the number of cores or one."
        )
    
    # If the number of traces is one, then we need to duplicate the trace for each core
    if (len(tracepaths[0]) == 1 and args.cores > 1):
        for i in range(len(tracepaths)):
            for j in range(args.cores - 1):
                tracepaths[i].append(tracepaths[i][0])
    
    # print(tracepaths)

    output_dir = pathlib.Path(args.output)

    # Configure and make ChampSim
    if (not (pathlib.Path("bin") / binary_name).exists()) or args.force_build:
        build_process = subprocess.run(
            ["./build_champsim.sh", args.predictor, args.l1d, args.l2c, args.llc_replacement, str(args.cores)],
            capture_output=True,
            text=True,
            check=True,
        )
        if not (args.quiet):
            print("ChampSim built. Printing STDOUT of ./build_champsim.sh")
            print(build_process.stdout)
            print("\nPrinting STDERR of ./build_champsim.sh")
            print(build_process.stderr)
            print("\n")

    # Run the simulations
    for tracepath in tracepaths:
        run_simulation(
            trace_path=tracepath,
            binary_name=binary_name,
            output_dir=output_dir,
            run_id=run_id,
        )


if __name__ == "__main__":
    main()
