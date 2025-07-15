import shlex
import subprocess
import sys
from dataclasses import dataclass, field
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
    protoc_plugin: Optional[str] = None

    """Extra parameters to be passed to the protoc plugin.
    (https://github.com/protocolbuffers/protobuf/pull/2284)"""
    options: List[str] = field(default_factory=list)


@dataclass
class Files:
    inputs: List[Path]
    outputs: List[Path]


def _check_bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"hatch-protobuf: {name} must be true or false")
    return value


def _check_str(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"hatch-protobuf: {name} must be a string")
    return value


def _check_str_opt(name: str, value: Any) -> Optional[str]:
    if value is None:
        return value
    if not isinstance(value, str):
        raise RuntimeError(f"hatch-protobuf: {name} must be a string")
    return value


def _check_list(name: str, value: Any) -> List[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"hatch-protobuf: {name} must be a list")
    return value


def _check_list_of_str(name: str, value: Any) -> List[str]:
    list_val = _check_list(name, value)
    for item in list_val:
        if not isinstance(item, str):
            raise RuntimeError(f"hatch-protobuf: {name} must be a list of strings")
    return list_val


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
        for path in self._library_paths:
            args.append("--proto_path")
            args.append(path)
        if self._get_bool_conf("import_site_packages", False):
            args.append("--proto_path")
            args.append(get_path("purelib"))
        for generator in self._generators:
            if generator.protoc_plugin:
                args.append(
                    f"--plugin=protoc-gen-{generator.name}={generator.protoc_plugin}"
                )
            args.append(f"--{generator.name}_out={generator.output_path}")
            for option in generator.options:
                args.append(f"--{generator.name}_opt={option}")

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

    def _get_bool_conf(self, name: str, default: bool) -> bool:
        return _check_bool(name, self.config.get(name, default))

    def _get_str_conf(self, name: str, default: str) -> str:
        return _check_str(name, self.config.get(name, default))

    def _get_list_conf(self, name: str, default: List[Any]) -> List[Any]:
        return _check_list(name, self.config.get(name, default))

    def _get_list_of_str_conf(self, name: str, default: List[str]) -> List[str]:
        return _check_list_of_str(name, self.config.get(name, default))

    @cached_property
    def _proto_paths(self) -> List[str]:
        return self._get_list_of_str_conf("proto_paths", [self._default_proto_path])

    @cached_property
    def _library_paths(self) -> List[str]:
        return self._get_list_of_str_conf("library_paths", [])

    @cached_property
    def _generators(self) -> List[Generator]:
        output_path = self._get_str_conf("output_path", self._default_proto_path)

        generators = [
            Generator(
                name="python",
                outputs=["{proto_path}/{proto_name}_pb2.py"],
                output_path=Path(output_path),
            )
        ]
        if self._get_bool_conf("generate_pyi", True):
            generators.append(
                Generator(
                    name="pyi",
                    outputs=["{proto_path}/{proto_name}_pb2.pyi"],
                    output_path=Path(output_path),
                )
            )
        if self._get_bool_conf("generate_grpc", True):
            generators.append(
                Generator(
                    name="grpc_python",
                    outputs=["{proto_path}/{proto_name}_pb2_grpc.py"],
                    output_path=Path(output_path),
                )
            )

        for g in self._get_list_conf("generators", []):
            generators.append(
                Generator(
                    name=_check_str("generators.name", g["name"]),
                    outputs=_check_list_of_str("generators.outputs", g["outputs"]),
                    output_path=Path(
                        _check_str(
                            "generators.output_path", g.get("output_path", output_path)
                        )
                    ),
                    protoc_plugin=_check_str_opt(
                        "generators.protoc_plugin", g.get("protoc_plugin", None)
                    ),
                    options=_check_list_of_str(
                        "generators.options", g.get("options", [])
                    ),
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
