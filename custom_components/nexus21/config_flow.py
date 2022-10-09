"""Config flow for nexus21."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from urllib.parse import urlparse

from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.components.dhcp import DhcpServiceInfo
from homeassistant.helpers import config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME
from homeassistant.helpers.device_registry import format_mac
from homeassistant.util.network import is_link_local, is_ip_address, is_host_valid

from .const import DOMAIN


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_MAC): cv.string,
    }
)


class Nexus21ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nexus21 TV Lift."""

    VERSION = 1

    _discovery_info: DhcpServiceInfo | None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # TODO: validate ip address or hostname with is_host_valid, mac address is valid format.
            errors = []  # await self._async_validate_input(user_input[CONF_IP_ADDRESS])
            if not errors:
                await self.async_set_unique_id(user_input[CONF_MAC])
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS],
                        CONF_MAC: format_mac(user_input[CONF_MAC]),
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> FlowResult:
        await self.async_set_unique_id(discovery_info.macaddress)

        self._abort_if_unique_id_configured(
            updates={
                CONF_NAME: discovery_info.hostname,
                CONF_IP_ADDRESS: discovery_info.ip,
            }
        )

        self._discovery_info = discovery_info

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle confirmation flow for discovered lift motor."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_IP_ADDRESS: self._discovery_info.ip,
                    CONF_MAC: format_mac(self._discovery_info.macaddress),
                },
            )

        self.context["title_placeholders"] = {
            CONF_NAME: self._discovery_info.hostname,
            CONF_IP_ADDRESS: self._discovery_info.ip,
        }

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=self._discovery_info.hostname
                    ): cv.string
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_IP_ADDRESS: self._discovery_info.ip,
            },
            last_step=True,
        )
