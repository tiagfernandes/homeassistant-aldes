"""Support for the Aldes sensors."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import (
    EntityCategory,
)
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.aldes.models import (
    AirMode,
    AntilegionellaCycle,
    CommandUid,
    HouseholdComposition,
    WaterMode,
)

from .const import (
    DOMAIN,
    FRIENDLY_NAMES,
    MANUFACTURER,
)
from .entity import AldesEntity, DeviceContext

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    selects = []

    for device_key, device in (coordinator.data or {}).items():
        if not device or not device.indicator:
            continue
        context = DeviceContext(
            device_key=device_key,
            device=device,
            config_entry=entry,
        )

        # Collect current air mode entity
        selects.append(
            AldesAirModeEntity(
                coordinator,
                context,
            )
        )

        # Collect entities if AquaAir reference
        if device.reference == "TONE_AQUA_AIR":
            # Collect current water mode entity
            selects.append(
                AldesWaterModeEntity(
                    coordinator,
                    context,
                )
            )

            # Collect current household composition entity
            selects.append(
                AldesHouseholdCompositionEntity(
                    coordinator,
                    context,
                )
            )

            # Collect current antilegionella cycle entity
            selects.append(
                AldesAntilegionellaCycleEntity(
                    coordinator,
                    context,
                )
            )

    async_add_entities(selects)


class AldesAirModeEntity(AldesEntity, SelectEntity):
    """Representation of the current air mode select entity."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, context)
        self._state = None
        self._attr_current_option: AirMode | None = None
        self._attr_options: list[AirMode] = [
            AirMode.OFF,
            AirMode.HEAT_COMFORT,
            AirMode.HEAT_ECO,
            AirMode.HEAT_PROG_A,
            AirMode.HEAT_PROG_B,
            AirMode.COOL_COMFORT,
            AirMode.COOL_BOOST,
            AirMode.COOL_PROG_A,
            AirMode.COOL_PROG_B,
        ]
        self._attr_display_names: dict[AirMode, str] = {
            AirMode.OFF: "Off",
            AirMode.HEAT_COMFORT: "Chauffage Comfort",
            AirMode.HEAT_ECO: "Chauffage Eco",
            AirMode.HEAT_PROG_A: "Chauffage Prog A",
            AirMode.HEAT_PROG_B: "Chauffage Prog B",
            AirMode.COOL_COMFORT: "Rafraîchissement Comfort",
            AirMode.COOL_BOOST: "Rafraîchissement Boost",
            AirMode.COOL_PROG_A: "Rafraîchissement Prog A",
            AirMode.COOL_PROG_B: "Rafraîchissement Prog B",
        }
        self._retry_mode_task: asyncio.Task | None = None
        # Track pending mode changes for retry mechanism
        self._pending_mode_change: dict[str, Any] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.device_identifier}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_air_mode"

    def _friendly_name_internal(self) -> str | None:
        """Return friendly name for the air mode select entity."""
        return "Mode Air"

    @property
    def options(self) -> list[str]:
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[AirMode(mode)] for mode in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Retourner l'option actuelle à partir du mode interne."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(
                self._attr_current_option, self._attr_current_option
            )
        return None

    @property
    def state(self) -> str:
        """Return the current state of the air mode."""
        # Access the `current_air_mode` from the coordinator data
        device = self._get_device()
        if device is None or device.indicator is None:
            return "unavailable"
        mode = device.indicator.current_air_mode
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        device = self._get_device()
        return bool(device and device.is_connected)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:air-conditioner"

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option),
            None,
        )
        if selected_option is None:
            _LOGGER.warning("Unknown air mode selection: %s", option)
            return

        await self._set_air_mode(
            selected_option.value if isinstance(selected_option, AirMode) else "Unknown"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

        # Cancel any existing retry task
        if self._retry_mode_task and not self._retry_mode_task.done():
            self._retry_mode_task.cancel()

        # Store the pending change for retry verification
        self._pending_mode_change = {
            "expected_mode": selected_option,
        }

        # Schedule retry check
        self._retry_mode_task = asyncio.create_task(
            self._verify_air_mode_change_after_delay()
        )

    async def _set_air_mode(self, mode: str) -> None:
        """Send a command to change the air mode."""
        await self.coordinator.api.change_mode(self.modem, mode, CommandUid.AIR_MODE)

    async def _verify_air_mode_change_after_delay(self) -> None:
        """Verify air mode change after delay and retry if needed."""
        try:
            await asyncio.sleep(60)

            if not self._pending_mode_change:
                return

            # Force a coordinator refresh to get latest data
            await self.coordinator.async_request_refresh()

            # Wait a bit for the refresh to complete
            await asyncio.sleep(2)

            # Check if coordinator data is available
            if self.coordinator.data is None:
                _LOGGER.warning(
                    "Coordinator data is None, cannot verify air mode change"
                )
                self._pending_mode_change = None
                return

            expected_mode = self._pending_mode_change["expected_mode"]
            device = self._get_device()
            if device is None or device.indicator is None:
                return
            current_mode = device.indicator.current_air_mode

            # If the mode hasn't changed, retry the API call
            if current_mode != expected_mode:
                _LOGGER.warning(
                    "Air mode not updated after 1 minute (expected: %s, actual: %s). Retrying API call...",
                    expected_mode,
                    current_mode,
                )

                # Retry the API call
                await self.coordinator.api.change_mode(
                    self.modem, expected_mode.value, CommandUid.AIR_MODE
                )

                # Force another refresh after retry
                await asyncio.sleep(2)
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.debug(
                    "Air mode successfully updated to %s",
                    expected_mode,
                )

            # Clear pending change
            self._pending_mode_change = None

        # Use generic verification method
        await self._verify_state_change_after_delay(
            get_current_fn=get_current_mode,
            expected_value=expected_mode,
            retry_fn=retry_mode,
            threshold=0,
            command_name="air mode",
            max_retries=3,
        )


class AldesWaterModeEntity(AldesEntity, SelectEntity):
    """Representation of the current water mode sensor as a selectable option."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, context)
        self._state = None
        self._attr_current_option: WaterMode | None = None
        self._attr_options: list[WaterMode] = [
            WaterMode.OFF,
            WaterMode.ON,
            WaterMode.BOOST,
        ]
        self._attr_display_names: dict[WaterMode, str] = {
            WaterMode.OFF: "Off",
            WaterMode.ON: "On",
            WaterMode.BOOST: "Boost",
        }
        self._retry_water_mode_task: asyncio.Task | None = None
        # Track pending mode changes for retry mechanism
        self._pending_water_mode_change: dict[str, Any] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.device_identifier}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_hot_water_mode"

    def _friendly_name_internal(self) -> str | None:
        """Return friendly name for the hot water mode select entity."""
        return "Mode Eau chaude"

    @property
    def options(self) -> list[str]:
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[mode] for mode in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Retourner l'option actuelle à partir du mode interne."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(
                self._attr_current_option, self._attr_current_option
            )
        return None

    @property
    def state(self) -> str:
        """Return the current state of the watter mode."""
        # Access the `current_water_mode` from the coordinator data
        device = self._get_device()
        if device is None or device.indicator is None:
            return "unavailable"
        mode = device.indicator.current_water_mode
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        device = self._get_device()
        return bool(device and device.is_connected)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:water-boiler"

    async def async_select_option(self, option: str) -> None:
        """Set the water mode to the selected option."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option),
            None,
        )
        if selected_option is None:
            _LOGGER.warning("Unknown water mode selection: %s", option)
            return

        await self._set_water_mode(
            selected_option.value
            if isinstance(selected_option, WaterMode)
            else "Unknown"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

        # Cancel any existing retry task
        if self._retry_water_mode_task and not self._retry_water_mode_task.done():
            self._retry_water_mode_task.cancel()

        # Store the pending change for retry verification
        self._pending_water_mode_change = {
            "expected_mode": selected_option,
        }

        # Schedule retry check
        self._retry_water_mode_task = asyncio.create_task(
            self._verify_water_mode_change_after_delay()
        )

    async def _set_water_mode(self, mode: str) -> None:
        """Send a command to change the water mode."""
        await self.coordinator.api.change_mode(self.modem, mode, CommandUid.HOT_WATER)

    async def _verify_water_mode_change_after_delay(self) -> None:
        """Verify water mode change after delay and retry if needed."""
        # Store expected mode for closure
        expected_mode = self._attr_current_option

        if expected_mode is None:
            return

        def get_current_mode() -> WaterMode:
            """Get current water mode from device."""
            device = self._get_device()
            if device is None or device.indicator is None:
                return WaterMode.OFF
            return device.indicator.current_water_mode

        async def retry_mode() -> None:
            """Retry changing the mode."""
            await self.coordinator.api.change_mode(
                self.modem, expected_mode.value, CommandUid.HOT_WATER
            )

        # Use generic verification method
        await self._verify_state_change_after_delay(
            get_current_fn=get_current_mode,
            expected_value=expected_mode,
            retry_fn=retry_mode,
            threshold=0,
            command_name="water mode",
            max_retries=3,
        )


class AldesHouseholdCompositionEntity(AldesEntity, SelectEntity):
    """Representation of the current household composition sensor."""

    _state = None
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, context)
        self._attr_current_option: HouseholdComposition | None = None
        self._attr_options: list[HouseholdComposition] = [
            HouseholdComposition.TWO,
            HouseholdComposition.THREE,
            HouseholdComposition.FOUR,
            HouseholdComposition.FIVE,
            HouseholdComposition.FIVE_AND_MORE,
        ]
        self._attr_display_names: dict[HouseholdComposition, str] = {
            HouseholdComposition.TWO: "Deux personnes",
            HouseholdComposition.THREE: "Trois personnes",
            HouseholdComposition.FOUR: "Quatre personnes",
            HouseholdComposition.FIVE: "Cinq personnes",
            HouseholdComposition.FIVE_AND_MORE: "Cinq personnes et plus",
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.device_identifier}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_household_composition"

    def _friendly_name_internal(self) -> str | None:
        """Return friendly name for the household composition select entity."""
        return "Composition du foyer"

    @property
    def options(self) -> list[str]:
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[mode] for mode in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Retourner l'option actuelle."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(
                self._attr_current_option, self._attr_current_option
            )
        return None

    @property
    def state(self) -> str | None:
        """Return the current state of household composition."""
        # Access the `people` from the coordinator data
        device = self._get_device()
        if device is None or not device.indicator or not device.indicator.settings:
            return "unavailable"
        try:
            if device.indicator.settings.people is None:
                return "unknown"
            people = HouseholdComposition(str(device.indicator.settings.people))
            return self._attr_display_names.get(people, str(people))
        except ValueError:
            # Handle invalid values
            return "unknown"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        device = self._get_device()
        return bool(device and device.is_connected)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:account-group"

    async def async_select_option(self, option: str) -> None:
        """Set the value to the selected option."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option),
            None,
        )
        if selected_option is None:
            _LOGGER.warning("Unknown household composition selection: %s", option)
            return

        await self._set_household_composition(
            selected_option.value
            if isinstance(selected_option, HouseholdComposition)
            else "Unknown"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_household_composition(self, people: str) -> None:
        """Send a command to change the value."""
        await self.coordinator.api.change_people(self.modem, people)


class AldesAntilegionellaCycleEntity(AldesEntity, SelectEntity):
    """Representation of the current antilegionella cycle sensor."""

    _state = None
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, context)
        self._attr_current_option: AntilegionellaCycle | None = None
        self._attr_options: list[AntilegionellaCycle] = [
            AntilegionellaCycle.OFF,
            AntilegionellaCycle.MONDAY,
            AntilegionellaCycle.TUESDAY,
            AntilegionellaCycle.WEDNESDAY,
            AntilegionellaCycle.THURSDAY,
            AntilegionellaCycle.FRIDAY,
            AntilegionellaCycle.SATURDAY,
            AntilegionellaCycle.SUNDAY,
        ]
        self._attr_display_names: dict[AntilegionellaCycle, str] = {
            AntilegionellaCycle.OFF: "Off",
            AntilegionellaCycle.MONDAY: "Lundi",
            AntilegionellaCycle.TUESDAY: "Mardi",
            AntilegionellaCycle.WEDNESDAY: "Mercredi",
            AntilegionellaCycle.THURSDAY: "Jeudi",
            AntilegionellaCycle.FRIDAY: "Vendredi",
            AntilegionellaCycle.SATURDAY: "Samedi",
            AntilegionellaCycle.SUNDAY: "Dimanche",
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.device_identifier}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_antilegionella_cycle"

    def _friendly_name_internal(self) -> str | None:
        """Return friendly name for the antilegionella cycle select entity."""
        return "Cycle antilegionelle"

    @property
    def options(self) -> list[str]:
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[mode] for mode in self._attr_options]

    @property
    def current_option(self) -> str | None:
        """Retourner l'option actuelle."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(
                self._attr_current_option, self._attr_current_option
            )
        return None

    @property
    def state(self) -> str:
        """Return the current state of antilegionella cycle."""
        # Access the `antilegio` from the coordinator data
        device = self._get_device()
        if device is None or not device.indicator or not device.indicator.settings:
            return "unavailable"
        if device.indicator.settings.antilegio is None:
            return "unknown"
        antilegio = AntilegionellaCycle(str(device.indicator.settings.antilegio))
        return self._attr_display_names.get(antilegio, str(antilegio))

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        device = self._get_device()
        return bool(device and device.is_connected)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:water-sync"

    async def async_select_option(self, option: str) -> None:
        """Set the value to the selected option."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option),
            None,
        )
        if selected_option is None:
            _LOGGER.warning("Unknown antilegionella selection: %s", option)
            return

        await self._set_antilegionella_cycle(
            selected_option.value
            if isinstance(selected_option, AntilegionellaCycle)
            else "Unknown"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_antilegionella_cycle(self, antilegio: str) -> None:
        """Send a command to change the value."""
        await self.coordinator.api.change_antilegio(self.modem, antilegio)
