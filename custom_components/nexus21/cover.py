from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_MAC

from . import Nexus21Entity
from .api import Nexus21IPModule, IPModuleStatusResponse, Nexus21Error

from .const import (
    NEXUS21_IP_MODULE,
    NEXUS21_COORDINATOR,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nexus21 covers."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            Nexus21Cover(
                data[NEXUS21_COORDINATOR],
                config_entry,
                data[NEXUS21_IP_MODULE],
            )
        ],
        True,
    )


class Nexus21Cover(Nexus21Entity, CoverEntity):
    """Representation of a Nexus21 cover."""

    """Set by async_update during HASS startup instead of __init__"""
    _status: IPModuleStatusResponse = None

    def __init__(
        self, coordinator, config_entry: ConfigEntry, ip_module: Nexus21IPModule
    ):
        """Initialize with API object."""
        super().__init__(coordinator, config_entry, ip_module)
        self._attr_supported_features = CoverEntityFeature.OPEN
        self._attr_supported_features |= CoverEntityFeature.CLOSE
        self._attr_unique_id = config_entry.data[CONF_MAC]
        # TODO add a config option to indicate whether this is horizontal or vertical. Also
        # think of a ceiling mount. Up or down is flipped compared to my pool TV.
        self._attr_device_class = CoverDeviceClass.GARAGE

    @property
    def is_closed(self) -> bool:
        return self._status.down and self._status.not_moving

    @property
    def is_closing(self) -> bool:
        return self._status.moving and self._status.up

    @property
    def is_open(self) -> bool:
        return self._status.up and self._status.not_moving

    @property
    def is_opening(self) -> bool:
        return self._status.down and self._status.moving

    @property
    def available(self) -> bool:
        """Return False if state has not been updated yet."""
        return self._status is not None

    async def async_close_cover(self, **kwargs: None) -> None:
        """Issue close command to cover."""
        if self.is_closing or self.is_closed:
            return

        try:
            duration = await self._ip_module.close(
                async_progress_callback=self._async_progress_callback
            )
        except Nexus21Error as error:
            raise HomeAssistantError(
                f"Opening of cover {self._ip_module.host} failed with error: {error}"
            ) from error

    async def async_open_cover(self, **kwargs: None) -> None:
        """Issue open command to cover."""
        if self.is_opening or self.is_open:
            return

        try:
            duration = await self._ip_module.open(
                async_progress_callback=self._async_progress_callback
            )
        except Nexus21Error as error:
            raise HomeAssistantError(
                f"Opening of cover {self._ip_module.host} failed with error: {error}"
            ) from error

    async def _async_progress_callback(self, status, done):
        self._status = status
        self.async_write_ha_state()

    async def async_update(self) -> None:
        status = await self._ip_module.get_status()
        self._status = status
