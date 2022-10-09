"""The Nexus21 integration."""
from __future__ import annotations

import logging
import async_timeout
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME

from .api import Nexus21IPModule
from .const import (
    DOMAIN,
    NEXUS21_IP_MODULE,
    NEXUS21_COORDINATOR,
    UPDATE_INTERVAL,
)

PLATFORMS: list[Platform] = [Platform.COVER]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nexus21 from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    # TODO 1. Create API instance
    # TODO 2. Validate the API connection (and authentication)
    # TODO 3. Store an API object for your platforms to access
    # hass.data[DOMAIN][entry.entry_id] = MyApi(...)

    ip_module = Nexus21IPModule(
        entry.data[CONF_IP_ADDRESS],
        session=aiohttp_client.async_get_clientsession(hass),
    )

    async def async_update_data():
        status = await ip_module.get_status()
        print(status)

    coordinator = Nexus21DataUpdateCoordinator(hass, entry, ip_module)

    hass.data[DOMAIN][entry.entry_id] = {
        NEXUS21_IP_MODULE: ip_module,
        NEXUS21_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class Nexus21DataUpdateCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, config_entry: ConfigEntry, ip_module: Nexus21IPModule):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Nexus21",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.ip_module = ip_module

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self.ip_module.get_status()
        except Exception as error:
            raise UpdateFailed(f"Error communicating with Nexus21 IP Module: {error}")


class Nexus21Entity(CoordinatorEntity):
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        ip_module: Nexus21IPModule,
    ) -> None:
        """Initialize class."""
        super().__init__(coordinator)
        self._ip_module = ip_module
        self._config_entry = config_entry

    @property
    def name(self):
        """Return the name if any, name can change if user changes it within MyQ."""
        return self._config_entry.data[CONF_NAME]

    @property
    def device_info(self):
        """Return the device_info of the device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.data[CONF_MAC])},
            manufacturer="Nexus21",
            model="IP Module",
            name=self._config_entry.data[CONF_NAME],
        )

    @property
    def available(self):
        """Return if the device is online."""
        return True
