import shlex
import subprocess
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from sysconfig import get_path
from typing import Any, Dict, List, Optional

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


@dataclass
class Generator:
    """A generator configuration."""

    """The name of the plugin."""
    name: str

    """Templates for paths that will be output, relative to ``output_path``."""
    outputs: List[str]

    """Where to write output files."""
    output_path: Path

    """The protoc plugin to use for this generator, if any. Will be passed as --plugin to protoc.
    This is useful for plugins that are not installed in the Python environment."""
    protoc_plugin: Optional[Path] = None


@dataclass
class Files:
    inputs: List[Path]
    outputs: List[Path]


class ProtocHook(BuildHookInterface):
    PLUGIN_NAME = "protobuf"

    def initialize(self, version: str, build_data: Dict[str, Any]) -> None:
        if not self._files.outputs:
            # nothing to do
            return

        self.app.display_info("Generating code from Protobuf files")

        args = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
        ]
        for path in self._proto_paths:
            args.append("--proto_path")
            args.append(path)
        if self.config.get("import_site_packages", False):
            args.append("--proto_path")
            args.append(get_path("purelib"))
        for generator in self._generators:
            if generator.protoc_plugin:
                args.append(
                    f"--plugin=protoc-gen-{generator.name}={generator.protoc_plugin}"
                )
            args.append(f"--{generator.name}_out={generator.output_path}")

        args += [str(p) for p in self._files.inputs]  # cast to str for debug output

        self.app.display_debug(f"Running {shlex.join(args)}")
        subprocess.run(args, cwd=self._root_path, check=True)

        build_data["artifacts"] += [p.as_posix() for p in self._files.outputs]

    def clean(self, versions: List[str]) -> None:
        if not self._files.outputs:
            # nothing to do
            return

        for output in self._files.outputs:
            (self._root_path / output).unlink(missing_ok=True)

    @cached_property
    def _root_path(self) -> Path:
        return Path(self.root)

    @cached_property
    def _default_proto_path(self) -> str:
        builder = self.build_config.builder
        for project_name in (
            builder.normalize_file_name_component(builder.metadata.core.raw_name),
            builder.normalize_file_name_component(builder.metadata.core.name),
        ):
            # check this first because that's what the wheel builder does
            if (self._root_path / project_name / "__init__.py").is_file():
                return "."
            if (self._root_path / "src" / project_name / "__init__.py").is_file():
                return "src"
        return "."

    @cached_property
    def _proto_paths(self) -> List[str]:
        return self.config.get("proto_paths", [self._default_proto_path])

    @cached_property
    def _generators(self) -> List[Generator]:
        gen_grpc = self.config.get("generate_grpc", True)
        gen_pyi = self.config.get("generate_pyi", True)

        output_path = self.config.get("output_path", self._default_proto_path)

        generators = [
            Generator(
                name="python",
                outputs=["{proto_path}/{proto_name}_pb2.py"],
                output_path=Path(output_path),
            )
        ]
        if gen_pyi:
            generators.append(
                Generator(
                    name="pyi",
                    outputs=["{proto_path}/{proto_name}_pb2.pyi"],
                    output_path=Path(output_path),
                )
            )
        if gen_grpc:
            generators.append(
                Generator(
                    name="grpc_python",
                    outputs=["{proto_path}/{proto_name}_pb2_grpc.py"],
                    output_path=Path(output_path),
                )
            )

        for g in self.config.get("generators", []):
            generators.append(
                Generator(
                    name=g["name"],
                    outputs=g["outputs"],
                    output_path=Path(g.get("output_path", output_path)),
                    protoc_plugin=g.get("protoc_plugin", None),
                )
            )

        return generators

    @cached_property
    def _files(self) -> Files:
        """Find input .proto files and the output files they will generate."""
        inputs = []
        rel_inputs = []
        for path in map(Path, self._proto_paths):
            abs_path = self._root_path / path
            for proto in abs_path.glob("**/*.proto"):
                # keep inputs relative to root directory, so as not to confuse protoc
                inputs.append(proto.relative_to(self._root_path))
                rel_inputs.append(proto.relative_to(abs_path))

        patterns = [
            (output, g.output_path) for g in self._generators for output in g.outputs
        ]

        outputs = []
        for proto in rel_inputs:
            proto_path = str(proto.parent)
            proto_name = str(proto.stem)
            for pattern, output_path in patterns:
                output = pattern.replace("{proto_name}", proto_name).replace(
                    "{proto_path}", proto_path
                )
                outputs.append(output_path / output)

        return Files(inputs=inputs, outputs=outputs)
