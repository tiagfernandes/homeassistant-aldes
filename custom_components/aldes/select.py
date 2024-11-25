"""Support for the Aldes sensors."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER, FRIENDLY_NAMES, ALDESMode
from .entity import AldesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    selects = []

    for product in coordinator.data:
        # Collect current water mode entity
        selects.append(
            AldesAirModeEntity(
                coordinator,
                entry,
                product["serial_number"],
                product["reference"],
                product["modem"]
            )
        )

        # Collect hot water tank entities if AquaAir reference
        if product['reference'] == "TONE_AQUA_AIR":
            # Collect current water mode entity
            selects.append(
                AldesWaterModeEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"]
                )
            )

    async_add_entities(selects)


class AldesAirModeEntity(AldesEntity, SelectEntity):
    """Representation of the current air mode select entity."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self._state = None
        self._attr_current_option = None
        self._attr_options = [
            ALDESMode.OFF,
            ALDESMode.HEAT_COMFORT,
            ALDESMode.HEAT_ECO,
            ALDESMode.HEAT_PROG_A,
            ALDESMode.HEAT_PROG_B,
            ALDESMode.COOL_COMFORT,
            ALDESMode.COOL_BOOST,
            ALDESMode.COOL_PROG_A,
            ALDESMode.COOL_PROG_B,
        ]
        self._attr_display_names = {
            ALDESMode.OFF: "Off",
            ALDESMode.HEAT_COMFORT: "Heat Comfort",
            ALDESMode.HEAT_ECO: "Heat Eco",
            ALDESMode.HEAT_PROG_A: "Heat Prog A",
            ALDESMode.HEAT_PROG_B: "Heat Prog B",
            ALDESMode.COOL_COMFORT: "Cool Comfort",
            ALDESMode.COOL_BOOST: "Cool Boost",
            ALDESMode.COOL_PROG_A: "Cool Prog A",
            ALDESMode.COOL_PROG_B: "Cool Prog B",
        }

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.product_serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.product_serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_air_mode"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return "Air mode"

    @property
    def options(self):
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[mode] for mode in self._attr_options]

    @property
    def current_option(self):
        """Retourner l'option actuelle à partir du mode interne."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(self._attr_current_option, self._attr_current_option)
        return None

    @property
    def state(self):
        """Return the current state of the air mode."""
        # Access the `current_air_mode` from the coordinator data
        mode = self.coordinator.data[0].get("indicator", {}).get("current_air_mode", "Unknown")
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self):
        """Return True if the entity is available."""
        return self.coordinator.data[0].get("isConnected", False)

    @property
    def icon(self) -> str:
        return "mdi:air-conditioner"

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option), None
        )

        await self._set_air_mode(selected_option)

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_air_mode(self, mode: str):
        """Send a command to change the air mode."""
        await self.coordinator.api.change_mode(
            self.modem,
            mode,
            0
        )


class AldesWaterModeEntity(AldesEntity, SelectEntity):
    """Representation of the current water mode sensor as a selectable option."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self._state = None
        self._attr_current_option = None
        self._attr_options = [
            ALDESMode.WATER_OFF,
            ALDESMode.WATER_ON,
            ALDESMode.WATER_BOOST,
        ]
        self._attr_display_names = {
            ALDESMode.WATER_OFF: 'Off',
            ALDESMode.WATER_ON: 'On',
            ALDESMode.WATER_BOOST: 'Boost',
        }

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.product_serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.product_serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_water_mode"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return "Water mode"

    @property
    def options(self):
        """Retourner la liste des options disponibles."""
        # Convertir les options internes en noms affichés
        return [self._attr_display_names[mode] for mode in self._attr_options]

    @property
    def current_option(self):
        """Retourner l'option actuelle à partir du mode interne."""
        # Si l'option actuelle est définie, la convertir en son nom lisible
        if self._attr_current_option:
            return self._attr_display_names.get(self._attr_current_option, self._attr_current_option)
        return None

    @property
    def state(self):
        """Return the current state of the watter mode."""
        # Access the `current_water_mode` from the coordinator data
        mode = self.coordinator.data[0].get("indicator", {}).get("current_water_mode", "Unknown")
        return self._attr_display_names.get(mode, mode)

    @property
    def available(self):
        """Return True if the entity is available."""
        return self.coordinator.data[0].get("isConnected", False)

    @property
    def icon(self) -> str:
        return "mdi:water-boiler"

    async def async_select_option(self, option: str) -> None:
        """Set the water mode to the selected option."""
        # Convert the displayed option back to its original form
        selected_option = next(
            (key for key, value in self._attr_display_names.items() if value == option), None
        )

        await self._set_water_mode(selected_option)

        self._attr_current_option = selected_option
        self.async_write_ha_state()

    async def _set_water_mode(self, mode: str):
        """Send a command to change the water mode."""
        await self.coordinator.api.change_mode(
            self.modem,
            mode,
            1
        )
