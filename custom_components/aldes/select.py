"""Support for the Aldes sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import (
    EntityCategory,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    FRIENDLY_NAMES,
    MANUFACTURER,
    AirMode,
    AntilegionellaCycle,
    HouseholdComposition,
    WaterMode,
)
from .api import CommandUid
from .entity import AldesEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    selects = []

    # Collect current water mode entity
    selects.append(
        AldesAirModeEntity(
            coordinator,
            entry,
        )
    )

    # Collect entities if AquaAir reference
    if coordinator.data.reference == "TONE_AQUA_AIR":
        # Collect current water mode entity
        selects.append(
            AldesWaterModeEntity(
                coordinator,
                entry,
            )
        )

        # Collect current household composition entity
        selects.append(
            AldesHouseholdCompositionEntity(
                coordinator,
                entry,
            )
        )

        # Collect current antilegionella cycle entity
        selects.append(
            AldesAntilegionellaCycleEntity(
                coordinator,
                entry,
            )
        )

    async_add_entities(selects)


class AldesAirModeEntity(AldesEntity, SelectEntity):
    """Representation of the current air mode select entity."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, config_entry)
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_air_mode"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
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
        mode = self.coordinator.data.indicator.current_air_mode
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.data.is_connected

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

        await self._set_air_mode(
            selected_option.value if isinstance(selected_option, AirMode) else "Unknow"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_air_mode(self, mode: str) -> None:
        """Send a command to change the air mode."""
        await self.coordinator.api.change_mode(self.modem, mode, CommandUid.AIR_MODE)


class AldesWaterModeEntity(AldesEntity, SelectEntity):
    """Representation of the current water mode sensor as a selectable option."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, config_entry)
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_hot_water_mode"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
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
        mode = self.coordinator.data.indicator.current_water_mode
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.data.is_connected

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

        await self._set_water_mode(
            selected_option.value
            if isinstance(selected_option, WaterMode)
            else "Unknow"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_water_mode(self, mode: str) -> None:
        """Send a command to change the water mode."""
        await self.coordinator.api.change_mode(self.modem, mode, CommandUid.HOT_WATER)


class AldesHouseholdCompositionEntity(AldesEntity, SelectEntity):
    """Representation of the current household composition sensor."""

    _state = None
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, config_entry)
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
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_household_composition"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
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
    def state(self) -> str:
        """Return the current state of household composition."""
        # Access the `people` from the coordinator data
        people = HouseholdComposition(
            str(self.coordinator.data.indicator.settings.people)
        )
        return self._attr_display_names.get(people, str(people))

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.data.is_connected

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

        await self._set_household_composition(
            selected_option.value
            if isinstance(selected_option, HouseholdComposition)
            else "Unknow"
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
        config_entry: ConfigEntry,
    ) -> None:
        """Innitialize."""
        super().__init__(coordinator, config_entry)
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
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_antilegionella_cycle"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
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
        antilegio = AntilegionellaCycle(
            str(self.coordinator.data.indicator.settings.antilegio)
        )
        return self._attr_display_names.get(antilegio, str(antilegio))

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.data.is_connected

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

        await self._set_antilegionella_cycle(
            selected_option.value
            if isinstance(selected_option, AntilegionellaCycle)
            else "Unknow"
        )

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_antilegionella_cycle(self, antilegio: str) -> None:
        """Send a command to change the value."""
        await self.coordinator.api.change_antilegio(self.modem, antilegio)
