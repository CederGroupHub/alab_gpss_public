"""This module contains the Moving task."""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from traceback import format_exc

import networkx as nx
from alab_management.user_input import request_user_input
from pydantic import BaseModel

from alab_gpss.utils import GPSSBaseTask


class GPSSMoving(GPSSBaseTask):
    """This class represents the Moving task."""

    class MovingResult(BaseModel):
        start_time: float
        end_time: float
        duration: float

    MOVING_GRAPH_PATH: Path = (
        Path(__file__).parent / "moving_graph" / "moving_graph.pkl"
    )

    def __init__(
        self,
        destination: str,
        consum_type: str,
        source: str | None = None,
        *args,
        **kwargs,
    ):
        """Initialize the Moving task."""
        super().__init__(*args, **kwargs)

        # if the source is set, we will ignore the sample
        self.source = source
        self.destination = destination
        self.consum_type = consum_type

    def validate(self) -> bool:
        if not self.samples and not self.source:
            return False
        if self.source is None and len(self.samples) != 1:
            return False
        if self.consum_type not in {
            "cap",
            "cap_sieved",
            "crucible",
            "vial",
            "xrd_sample_holder",
            "dac_lid",
            "furnace_rack",
        }:
            return False
        return True

    def load_moving_graph(self) -> nx.DiGraph:
        """Load the moving graph."""
        return pickle.load(open(self.MOVING_GRAPH_PATH, "rb"))

    def get_shortest_path(
        self,
    ) -> tuple[list[str], list[dict[str, str | list[str | dict[str, str]]]]]:
        """Get the shortest path between two positions."""
        moving_graph = self.load_moving_graph()

        if self.source not in moving_graph.nodes:
            raise ValueError(f"Source {self.source} not in moving graph.")
        if self.destination not in moving_graph.nodes:
            raise ValueError(f"Destination {self.destination} not in moving graph.")

        sub_graph = nx.subgraph_view(
            moving_graph,
            filter_node=lambda n: self.consum_type
            in nx.get_node_attributes(moving_graph, "type", default=tuple())[n],
        )
        path = nx.shortest_path(sub_graph, source=self.source, target=self.destination)
        # translate the path into a list of (robot, program_list)
        program_list = []

        for i in range(len(path) - 1):
            program = sub_graph.get_edge_data(path[i], path[i + 1])
            if program_list and program_list[-1]["robot"] == program["robot"]:
                program_list[-1]["program_list"].append(
                    {
                        "start": path[i],
                        "end": path[i + 1],
                        "programs": program["programs"],
                    }
                )
            else:
                program_list.append(
                    {
                        "robot": program["robot"],
                        "program_list": [
                            {
                                "start": path[i],
                                "end": path[i + 1],
                                "programs": program["programs"],
                            }
                        ],
                    }
                )

        return path, program_list

    def get_resource_request(self, path, program_list):
        """Get the resource request for the Moving task."""
        request = {}
        for position in path:
            parent_device = self.lab_view.get_sample_position_parent_device(position)
            request.setdefault(parent_device, {})
            if parent_device is not None:
                position_pieces = position.split("/")
                if parent_device in position_pieces:
                    position_pieces.remove(parent_device)
                position_processed = "/".join(position_pieces)
            else:
                position_processed = position
            request[parent_device][
                position_processed
            ] = 1  # need one position per parent.

        for program in program_list:
            robot = program["robot"]
            if robot not in request:
                request[robot] = {}

        return request

    def result_specification(self) -> type[BaseModel]:
        """Return the result specification for the Moving task."""
        return self.MovingResult

    def run(self):
        """Run the Moving task."""
        if self.source is None:
            sample = self.samples[0]
            self.source = self.lab_view.get_sample(sample).position
        else:
            sample = None

        if sample is not None:
            sample_entry = self.lab_view.get_sample(sample)

            if sample_entry.position == self.destination:
                return None

        path, program_list = self.get_shortest_path()
        request = self.get_resource_request(path, program_list)

        start_time = time.time()

        with self.lab_view.request_resources(request) as (devices, sample_positions):
            for segment in program_list:
                robot = devices[segment["robot"]]
                program_list_ = segment["program_list"]

                for program in program_list_:

                    robot.set_message(
                        f"Moving sample {sample} from {program['start']} to {program['end']}"
                    )

                    while True:
                        try:
                            robot.run_programs(program["programs"])
                        except Exception:
                            response = request_user_input(
                                task_id=self.task_id,
                                prompt=f"Error while moving sample from {program['start']} to {program['end']} "
                                f"(1) Set the robot arm to home position;\n"
                                f"(2) If you want to skip this movement, put sample to {program['end']}. If you want to "
                                f"retry the task, put sample to {program['start']}. Press abort to stop.\n"
                                f"The error is {format_exc()}.",
                                options=["Skip", "Retry", "Abort"],
                            )
                            if response == "Abort":
                                raise
                            if response == "Skip":
                                break
                        else:
                            break

                    robot.set_message("")

                    if sample is not None:
                        self.lab_view.move_sample(
                            sample=self.lab_view.get_sample(sample).sample_id,
                            position=program["end"],
                        )

        end_time = time.time()
        return {
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
        }
