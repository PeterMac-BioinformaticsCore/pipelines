from abc import ABC, abstractmethod
import re
from typing import List, Dict, Optional, Any

from Pipeline.tool.tool import Tool, ToolArgument, ToolInput, ToolOutput, ToolTypes

import cwlgen.cwlgen as cwl
from Pipeline.types.common_data_types import Stdout, Array
from Pipeline.utils import convert_expression_to_wdl
from Pipeline.utils.logger import Logger
from Pipeline.utils.validators import Validators


class CommandTool(Tool, ABC):
    """
    Notes:
        - If you're thinking about secondary files, DON'T!! Consider creating a new DataType.
        - This class is similar to how RABIX COMPOSER creates the tools
        - You can subclass and override whichever fields you'd like, including the INPUTS / OUTPUTS!
        - Take note which options you can provide to the ToolInput and ToolOutput.
    """

    def id(self):
        return self.tool().lower()

    @staticmethod
    @abstractmethod
    def tool():
        raise Exception(f"subclass MUST implement 'tool' method")

    @classmethod
    def full_name(cls):
        if cls.version() is not None:
            return f"{cls.tool()}/{cls.version()}"
        return cls.tool()

    @staticmethod
    def docker():
        return "ubuntu:latest"

    @staticmethod
    @abstractmethod
    def base_command():
        raise Exception("Subclass MUST implement the 'base_command' method with str or [str] return types")

    def memory(self) -> Optional[int]:
        return None

    def cpus(self) -> Optional[int]:
        return None

    def arguments(self) -> Optional[List[ToolArgument]]:
        return None

    @classmethod
    def type(cls):
        return ToolTypes.CommandTool

    @staticmethod
    def environment_variables() -> Optional[Dict[str, str]]:
        return None

    @staticmethod
    def requirements() -> Optional[List[cwl.Requirement]]:
        return None

    def cwl(self, with_docker=True) -> Dict[str, Any]:

        stdouts = [o.output_type for o in self.outputs() if isinstance(o.output_type, Stdout) and o.output_type.stdoutname]
        stdout = stdouts[0].stdoutname if len(stdouts) > 0 else None

        tool = cwl.CommandLineTool(
            tool_id=self.id(),
            base_command=self.base_command(),
            label=self.id(),
            doc=self.doc(),
            # cwl_version=Cwl.kCUR_VERSION,
            stdin=None,
            stderr=None,
            stdout=stdout
        )

        tool.requirements.extend([
            cwl.InlineJavascriptReq()
        ])

        if self.requirements():
            tool.requirements.extend(self.requirements())

        if with_docker:
            tool.requirements.append(cwl.DockerRequirement(
                docker_pull=self.docker(),
                # docker_load=None,
                # docker_file=None,
                # docker_import=None,
                # docker_image_id=None,
                # docker_output_dir=None
            ))

        tool.inputs.extend(i.cwl() for i in self.inputs())
        tool.outputs.extend(o.cwl() for o in self.outputs())
        args = self.arguments()
        if args:
            tool.arguments.extend(a.cwl() for a in self.arguments())

        return tool.get_dict()

    def wdl(self, with_docker=True):
        import wdlgen.wdlgen as wdl

        # Todo: Move this to python-wdlgen
        if not Validators.validate_identifier(self.id()):
            raise Exception(f"The identifier '{self.id()}' for class '{self.__class__.__name__}' was not validated by "
                            f"'{Validators.identifier_regex}' (must start with letters, and then only contain letters, "
                            f"numbers or an underscore)")

        ins, outs = [], []
        for i in self.inputs():
            wd = i.input_type.wdl()
            if isinstance(wd, list):
                ins.extend(wdl.Input(w, i.id()) for w in wd)
            else:
                ins.append(wdl.Input(wd, i.id()))

        for o in self.outputs():

            if isinstance(o.output_type, Stdout):
                expression = "stdout()"
            else:

                glob = convert_expression_to_wdl(o.glob)
                if glob is not None and "*" in glob:
                    glob = f'glob({glob})'
                    if not isinstance(o.output_type, Array):
                        Logger.warn(f"The command tool '{self.id()}.{o.tag}' used a star-bind (*) glob to find the output, "
                                    f"but the return type was not an array. For WDL, the first element will be used, "
                                    f"ie: '{glob}[0]'")
                        glob = glob + "[0]"
                expression = glob

            outs.append(wdl.Output(o.output_type.wdl(), o.id(), expression))

        command_ins = [

            wdl.Task.Command.CommandInput(
                name=i.id(),
                optional=i.input_type.optional,
                prefix=i.prefix,
                position=i.position,
                separate_value_from_prefix=i.separate_value_from_prefix,
                default=i.default if i.default else i.input_type.default()
            ) for i in self.inputs()] if self.inputs() else None

        command_args = None
        if self.arguments():
            command_args = []
            for a in self.arguments():
                if a.value is None:
                    val = None
                elif callable(getattr(a.value, "wdl", None)):
                    val = a.value.wdl()
                else:
                    val = a.value
                command_args.append(wdl.Task.Command.CommandArgument(a.prefix, val, a.position))

        command = wdl.Task.Command(self.base_command(), command_ins, command_args)

        r = wdl.Task.Runtime()
        if with_docker:
            r.add_docker(self.docker())

        return wdl.Task(self.id(), ins, outs, command, r)


    def help(self):
        import inspect
        path = inspect.getfile(self.__class__)

        ins = sorted(self.inputs(), key=lambda i: i.position if i.position is not None else 0)
        args = ""
        if self.arguments():
            args = " " + " ".join(f"{(a.prefix if a.prefix is not None else '') + ' ' if (a.prefix is not None and a.separate_value_from_prefix) else ''}{a.value}" for a in self.arguments())

        prefixes = " -" + "".join(i.prefix.replace("-", "").replace(" ", "") for i in ins if i.prefix is not None)

        docker = self.docker()

        command = (self.base_command() if isinstance(self.base_command(), str) else " ".join(self.base_command())) \
                  + args + prefixes

        def input_format(t: ToolInput):
            prefix_with_space = ""
            if t.prefix is not None:
                prefix_with_space = (t.prefix + ": ") if (t.separate_value_from_prefix is not False) else t.prefix
            return f"\t\t{t.tag} ({prefix_with_space}{t.input_type.id()}{('=' + str(t.default)) if t.default is not None else ''})" \
                f": {'' if t.doc is None else t.doc}"

        output_format = lambda t: f"\t\t{t.tag} ({t.output_type.id()}): {'' if t.doc is None else t.doc}"

        requiredInputs = "\n".join(input_format(x) for x in ins if not x.optional)
        optionalInputs = "\n".join(input_format(x) for x in ins if x.optional)
        outputs = "\n".join(output_format(o) for o in self.outputs())

        return f"""
    Pipeline tool: {path} ({self.id()})
NAME
    {self.id()}

SYNOPSIS
    {command}

DOCKER
    {docker}

DOCUMENTATION URL
    {self.docurl() if self.docurl() else "No url provided"}

DESCRIPTION
    {self.doc() if self.doc() is not None else "No documentation provided"}

INPUTS:
    REQUIRED:
{requiredInputs}

    OPTIONAL:
{optionalInputs}

OUTPUTS:
{outputs}
"""
