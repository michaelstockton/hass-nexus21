import asyncio
import aiohttp
import time
import voluptuous as vol

from enum import Enum
from mimetypes import init
from typing import Any, Set, Awaitable, Callable, Literal, TypedDict, Optional, Union

# TODO
#   Keep a last known state
#   Convert strings to constants
#   Logger
#   Transistion timing in log statements
#   JSON Error codes
#   Tests


class Nexus21Command(Enum):
    UP = "UP"
    DOWN = "DOWN"
    MEM1 = "MEM1"
    MEM2 = "MEM2"
    MEM3 = "MEM3"


NEXUS21_TRANSITION_TIMEOUT = 30
NEXUS21_TRANSITION_POLL_INTERVAL = 1
NEXUS21_COMMANDS: Set[str] = set(["UP", "DOWN", "MEM1", "MEM2", "MEM3"])
NEXUS21_STATUS: str = "status"
NEXUS21_COMMAND: str = "command"
NEXUS21_SERVICES: Set[str] = [NEXUS21_STATUS, NEXUS21_COMMAND]

Nexus21ServiceCommands = Literal["UP", "DOWN", "MEM1", "MEM2", "MEM3"]


class Response(TypedDict):
    STATUS: Literal["OK", "ERROR"]
    DESCRIPTION: Optional[Any]


class StatusResponse(Response):
    VERTICAL: Literal["UP", "DOWN", "MOVING", "MEM1", "MEM2", "MEM3"]
    HORIZONTAL: Literal[
        "LEFT", "CENTER", "RIGHT", "MOVING", "NA", "MEM1", "MEM2", "MEM3"
    ]
    EXTCMD: Optional[Any]
    DESCRIPTION: Optional[Any]


ResponseSchema = vol.Schema(
    {
        vol.Required("STATUS"): vol.All(str, vol.In(["OK", "ERROR"])),
    },
    extra=vol.ALLOW_EXTRA,
)

StatusResponseSchema = ResponseSchema.extend(
    {
        vol.Required("VERTICAL"): vol.All(
            str, vol.In(["UP", "DOWN", "MOVING", "ERROR"])
        ),
        vol.Required("HORIZONTAL"): vol.All(
            str,
            vol.In(
                [
                    "LEFT",
                    "CENTER",
                    "RIGHT",
                    "MOVING",
                    "NA",
                    "MEM1",
                    "MEM2",
                    "MEM3",
                ]
            ),
        ),
        vol.Optional("EXTCMD"): vol.Any(),
        vol.Optional("DESCRIPTION"): vol.Any(),
    }
)

CommandResponseSchema = ResponseSchema.extend(
    {
        vol.Optional("DESCRIPTION"): vol.Any(),
    }
)


class IPModuleResponse:
    _response: Response

    def __init__(self, response: Response):
        ResponseSchema(response)
        self._response = response

    @property
    def ok(self) -> bool:
        return self._response["STATUS"] == "OK"

    @property
    def not_ok(self) -> bool:
        return self._response["STATUS"] == "ERROR"

    @property
    def description(self) -> Union[str, None]:
        return self._response.get("DESCRIPTION")

    @property
    def status(self) -> str:
        return self._response["STATUS"]


class IPModuleStatusResponse(IPModuleResponse):

    _response: StatusResponse

    def __init__(self, response: StatusResponse):
        super().__init__(response)
        StatusResponseSchema(response)
        self._response = response

    @property
    def moving(self) -> bool:
        return (
            self._response["HORIZONTAL"] == "MOVING"
            or self._response["VERTICAL"] == "MOVING"
        )

    @property
    def not_moving(self) -> bool:
        return self.moving == False

    @property
    def up(self) -> bool:
        return (
            self._response["HORIZONTAL"] == "UP" or self._response["VERTICAL"] == "UP"
        )

    @property
    def down(self) -> bool:
        return (
            self._response["HORIZONTAL"] == "DOWN"
            or self._response["VERTICAL"] == "DOWN"
        )


class Nexus21Error(Exception):
    pass


class Nexus21CommandFailed(Nexus21Error):
    def __init__(self, command: str, response: IPModuleResponse):
        super().__init__(
            f"Sent '{command}' to IP Module but the result was an error '{response.status}'."
        )
        # Add description in here somehow {'({status["DESCRIPTION"]})' if description else ''}


class Nexus21InvalidCommandError(Nexus21Error):
    def __init__(self, command: str):
        super().__init__(
            f"'{command}' is an invalid command. A valid command must be member of {NEXUS21_COMMANDS}."
        )


class Nexus21InvalidResponse(Nexus21Error):
    def __init__(self, response: aiohttp.ClientResponse):
        super().__init__(
            f"Nexus21 IP module responded with HTTP status '{response.status}'. Response = {response}"
        )


class Nexus21IPModule:

    host: str
    _session: aiohttp.ClientSession
    _status: StatusResponse

    def __init__(
        self,
        host,
        session: aiohttp.ClientSession = None,
    ) -> None:
        self.host = host
        self._session = session or aiohttp.ClientSession()
        self._service_lock = (
            asyncio.Lock()
        )  # IP Module is limited to one HTTP call at a time.

    async def get_status(self) -> IPModuleStatusResponse:
        async with self._service_lock:
            async with self._session.get(
                f"http://{self.host}/api/{NEXUS21_STATUS}"
            ) as response:
                if response.status == 200:
                    json = await response.json()
                    return IPModuleStatusResponse(json)
                else:
                    raise Nexus21InvalidResponse(response)

    async def post_command(self, command: Nexus21ServiceCommands) -> IPModuleResponse:
        if command not in NEXUS21_COMMANDS:
            raise Nexus21InvalidCommandError(command)

        async with self._service_lock:
            async with self._session.post(
                f"http://{self.host}/api/{NEXUS21_COMMAND}",
                json={"COMMAND": command},
            ) as http_response:
                if http_response.status == 200:
                    module_response = IPModuleResponse(await http_response.json())
                    if module_response.not_ok:
                        raise Nexus21CommandFailed(command, module_response)
                    else:
                        return module_response
                else:
                    raise Nexus21InvalidResponse(http_response)

    async def close(
        self,
        async_progress_callback: Callable[
            [IPModuleStatusResponse, bool], Awaitable
        ] = None,
        timeout=NEXUS21_TRANSITION_TIMEOUT,
        poll_interval=NEXUS21_TRANSITION_POLL_INTERVAL,
    ) -> float:
        async def async_transition_callback(status: IPModuleStatusResponse):
            if status.moving and async_progress_callback:
                await async_progress_callback(status, False)
            elif status.not_moving and status.down and async_progress_callback:
                await async_progress_callback(status, True)

        return await asyncio.wait_for(
            self._transition(
                command=Nexus21Command.DOWN.name,
                async_transition_callback=async_transition_callback,
                poll_interval=poll_interval,
            ),
            timeout=timeout,
        )

    async def open(
        self,
        async_progress_callback: Callable[
            [IPModuleStatusResponse, bool], Awaitable
        ] = None,
        timeout=NEXUS21_TRANSITION_TIMEOUT,
        poll_interval=NEXUS21_TRANSITION_POLL_INTERVAL,
    ) -> float:
        async def async_transition_callback(status: IPModuleStatusResponse):
            if status.moving and async_progress_callback:
                await async_progress_callback(status, False)
            elif status.not_moving and status.up and async_progress_callback:
                await async_progress_callback(status, True)

        return await asyncio.wait_for(
            self._transition(
                command=Nexus21Command.UP.name,
                async_transition_callback=async_transition_callback,
                poll_interval=poll_interval,
            ),
            timeout=timeout,
        )

    async def _transition(
        self,
        command: Nexus21ServiceCommands,
        async_transition_callback: Callable[[IPModuleStatusResponse], Awaitable],
        poll_interval: int,
    ) -> float:
        began_at = time.time()
        starting_status = await self.get_status()
        previous_status = starting_status

        await self.post_command(command)

        while 1:
            current_status = await self.get_status()

            if previous_status.not_moving and current_status.not_moving:
                # This probably means the lift is already in the proper position
                await async_transition_callback(current_status)
                break
            elif previous_status.not_moving and current_status.moving:
                # The lift started moving
                await async_transition_callback(current_status)
            elif previous_status.moving and current_status.not_moving:
                # The lift finished moving
                await async_transition_callback(current_status)
                break
            elif previous_status.moving and current_status.moving:
                # No need to do anything
                pass
            elif current_status.not_ok:
                raise Nexus21CommandFailed(current_status)
            else:
                # If reached, some state is not accounted for and needs followup.
                raise AssertionError

            previous_status = current_status

            await asyncio.sleep(poll_interval)

        return time.time() - began_at
