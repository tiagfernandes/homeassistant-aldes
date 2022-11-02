"""AldesConnectEntity class"""
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class AldesConnectEntity(CoordinatorEntity):
    """AldesConnect entity"""

    def __init__(
        self, coordinator, config_entry, product_serial_number, reference, modem
    ):
        super().__init__(coordinator)
        self._attr_config_entry = config_entry
        self.product_serial_number = product_serial_number
        self.reference = reference
        self.modem = modem
