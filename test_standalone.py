#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone test menu for Aldes API without Home Assistant."""

import sys
from unittest.mock import MagicMock

# MOCK Home Assistant dependencies IMMEDIATELY
# This must be done before ANY import that might trigger custom_components loading
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["homeassistant.util.dt"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
sys.modules["homeassistant.helpers.entity_registry"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.entity"] = MagicMock()
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.components.sensor.const"] = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = MagicMock()
sys.modules["homeassistant.components.climate"] = MagicMock()
sys.modules["homeassistant.components.climate.const"] = MagicMock()
sys.modules["homeassistant.components.select"] = MagicMock()
sys.modules["homeassistant.components.number"] = MagicMock()
sys.modules["homeassistant.components.button"] = MagicMock()
sys.modules["voluptuous"] = MagicMock()

print(f"DEBUG: voluptuous in sys.modules: {'voluptuous' in sys.modules}")

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

# Add the current directory to path to allow imports from custom_components
sys.path.append(str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Set other loggers to WARNING to avoid noise
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Import API and models from the integration
try:
    from custom_components.aldes.api import AldesApi
    from custom_components.aldes.models import CommandUid, DataApiEntity
except ImportError as e:
    print(f"CRITICAL ERROR importing integration: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


class AldesTestMenu:
    """Interactive menu for testing Aldes API."""

    def __init__(self):
        """Initialize the test menu."""
        self.api: AldesApi | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.data: DataApiEntity | None = None
        self.session: aiohttp.ClientSession | None = None

    async def init_session(self) -> None:
        """Initialize aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close_session(self) -> None:
        """Close aiohttp session."""
        if self.session:
            await self.session.close()

    async def cleanup(self) -> None:
        """Cleanup resources before exiting."""
        # Stop the temperature worker
        if self.api:
            await self.api.stop_temperature_worker()
        # Close session
        await self.close_session()

    async def ainput(self, prompt: str = "") -> str:
        """Async input to avoid blocking the event loop."""
        return await asyncio.get_running_loop().run_in_executor(None, input, prompt)

    async def authenticate(self) -> bool:
        """Authenticate with Aldes API."""
        print("\n" + "=" * 50)
        print("   AUTHENTIFICATION")
        print("=" * 50)
        self.username = (await self.ainput("Nom d'utilisateur: ")).strip()
        self.password = (await self.ainput("Mot de passe: ")).strip()

        try:
            await self.init_session()
            assert self.session is not None
            self.api = AldesApi(self.username, self.password, self.session)
            await self.api.authenticate()
            
            # Start the temperature worker immediately after authentication
            await self.api._ensure_temperature_worker_started()
            
            print("\n✓ Authentification réussie!")
            return True
        except Exception as e:
            print(f"\n✗ Erreur d'authentification: {e}")
            return False

    async def fetch_data(self) -> bool:
        """Fetch account data from API."""
        if not self.api:
            print("\n✗ Veuillez d'abord vous authentifier.")
            return False

        try:
            print("\nRécupération des données...")
            raw_data = await self.api.fetch_data()

            if not raw_data:
                print("✗ Aucune donnée reçue de l'API.")
                return False

            # raw_data is already a dict of DataApiEntity objects because fetch_data returns it
            # (unlike the old standalone version which returned a dict)
            # We take the first device found for testing
            if isinstance(raw_data, dict) and raw_data:
                self.data = next(iter(raw_data.values()))
            elif isinstance(raw_data, DataApiEntity):
                self.data = raw_data
            else:
                # Fallback if fetch_data behavior changes
                print(f"⚠️ Type de données inattendu: {type(raw_data)}")
                return False

            print("✓ Données récupérées avec succès!\n")
            self._display_account_info()
            return True

        except Exception as e:
            print(f"✗ Erreur: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _display_account_info(self) -> None:
        """Display account information."""
        if not self.data:
            return

        print("=" * 50)
        print("   INFORMATIONS DU COMPTE")
        print("=" * 50)

        # Display device info
        print("\n--- Appareil principal ---")
        if self.data.modem:
            print(f"Modem: {self.data.modem}")
        if self.data.type:
            print(f"Type d'appareil: {self.data.type}")
        print(f"Connecté: {'✓ Oui' if self.data.is_connected else '✗ Non'}")

        # Display thermostats
        if self.data.indicator and self.data.indicator.thermostats:
            print("\n--- Thermostats disponibles ---")
            for i, thermostat in enumerate(self.data.indicator.thermostats, 1):
                print(f"{i}. {thermostat.name}")
                print(f"   ID: {thermostat.id}")
                print(f"   Température définie: {thermostat.temperature_set}°C")
                print(f"   Température actuelle: {thermostat.current_temperature}°C")
        else:
            print("\n✗ Aucun thermostat trouvé.")

        # Display indicator info
        if self.data.indicator:
            print("\n--- Mode global ---")
            # Handle both enum and int types
            air_mode = self.data.indicator.current_air_mode
            if hasattr(air_mode, 'value'):
                print(f"Mode air: {air_mode.value}")
            else:
                print(f"Mode air: {air_mode}")

            if self.data.indicator.settings and self.data.indicator.settings.people:
                people = self.data.indicator.settings.people
                if hasattr(people, 'value'):
                    print(f"Composition du foyer: {people.value}")
                else:
                    print(f"Composition du foyer: {people}")

    async def change_room_temperature(self) -> bool:
        """Change temperature for a room."""
        if not self.data or not self.data.indicator or not self.data.indicator.thermostats:
            print("\n✗ Veuillez d'abord récupérer les données.")
            return False

        print("\n" + "=" * 50)
        print("   CHANGER LA TEMPÉRATURE")
        print("=" * 50)
        print("\nThermostats disponibles:")

        thermostats = self.data.indicator.thermostats
        for i, thermostat in enumerate(thermostats, 1):
            print(
                f"{i}. {thermostat.name} "
                f"(ID: {thermostat.id}, "
                f"Température actuelle: {thermostat.current_temperature}°C)"
            )

        try:
            choice_str = await self.ainput("\nSélectionnez un thermostat (numéro): ")
            choice = int(choice_str.strip())
            if 1 <= choice <= len(thermostats):
                thermostat = thermostats[choice - 1]
                temp_input = await self.ainput("Nouvelle température (°C): ")
                temp = float(temp_input.strip())

                if temp < 5 or temp > 40:
                    print("✗ La température doit être entre 5°C et 40°C.")
                    return False

                print(
                    f"\nChangement de la température de {thermostat.name} "
                    f"à {temp}°C..."
                )

                if not self.api or not self.data.modem:
                    print("✗ Erreur: API non initialisée.")
                    return False

                # Call the API to set temperature
                await self.api.set_target_temperature(
                    self.data.modem, thermostat.id, thermostat.name, temp
                )

                # Note: set_target_temperature puts the request in a queue
                # The worker processes it asynchronously
                # In HA integration, optimistic state is used immediately
                print("✓ Température modifiée!")
                print("  (La requête a été envoyée au serveur)")
                print("  (Le changement peut prendre quelques instants)")
                return True
            else:
                print("✗ Sélection invalide.")
                return False
        except ValueError as e:
            print(f"✗ Saisie invalide: {e}")
            return False
        except Exception as e:
            print(f"✗ Erreur: {e}")
            return False

    async def change_air_mode(self) -> bool:
        """Change air mode."""
        if not self.api or not self.data or not self.data.modem:
            print("\n✗ Veuillez d'abord vous authentifier et récupérer les données.")
            return False

        print("\n" + "=" * 50)
        print("   CHANGER LE MODE AIR")
        print("=" * 50)
        print("\nModes disponibles:")

        modes = {
            "off": "Éteint",
            "heat_comfort": "Chauffage Confort",
            "heat_eco": "Chauffage Éco",
            "heat_prog_a": "Chauffage Programme A",
            "heat_prog_b": "Chauffage Programme B",
            "cool_comfort": "Rafraîchissement Confort",
            "cool_boost": "Rafraîchissement Boost",
            "cool_prog_a": "Rafraîchissement Programme A",
            "cool_prog_b": "Rafraîchissement Programme B",
        }

        mode_list = list(modes.items())
        for i, (key, name) in enumerate(mode_list, 1):
            print(f"{i}. {name}")

        try:
            choice_str = await self.ainput("\nSélectionnez un mode (numéro): ")
            choice = int(choice_str.strip())
            if 1 <= choice <= len(mode_list):
                mode_key, mode_name = mode_list[choice - 1]
                print(f"\nChangement du mode à {mode_name}...")
                await self.api.change_mode(self.data.modem, mode_key, CommandUid.AIR_MODE)
                print("✓ Mode modifié!")
                return True
            else:
                print("✗ Sélection invalide.")
                return False
        except ValueError as e:
            print(f"✗ Saisie invalide: {e}")
            return False
        except Exception as e:
            print(f"✗ Erreur: {e}")
            return False

    async def change_hot_water_mode(self) -> bool:
        """Change hot water mode."""
        if not self.api or not self.data or not self.data.modem:
            print("\n✗ Veuillez d'abord vous authentifier et récupérer les données.")
            return False

        # Check if device supports hot water
        # Note: device_type is now 'type' in DataApiEntity
        if self.data.type and "aquaair" not in self.data.type.lower():
            print("\n✗ Cet appareil ne supporte pas le contrôle de l'eau chaude.")
            return False

        print("\n" + "=" * 50)
        print("   CHANGER LE MODE EAU CHAUDE")
        print("=" * 50)
        print("\nModes disponibles:")

        modes = {
            "off": "Éteint",
            "on": "Allumé",
            "boost": "Boost",
        }

        mode_list = list(modes.items())
        for i, (key, name) in enumerate(mode_list, 1):
            print(f"{i}. {name}")

        try:
            choice_str = await self.ainput("\nSélectionnez un mode (numéro): ")
            choice = int(choice_str.strip())
            if 1 <= choice <= len(mode_list):
                mode_key, mode_name = mode_list[choice - 1]
                print(f"\nChangement du mode eau chaude à {mode_name}...")
                await self.api.change_mode(
                    self.data.modem, mode_key, CommandUid.HOT_WATER
                )
                print("✓ Mode eau chaude modifié!")
                return True
            else:
                print("✗ Sélection invalide.")
                return False
        except ValueError as e:
            print(f"✗ Saisie invalide: {e}")
            return False
        except Exception as e:
            print(f"✗ Erreur: {e}")
            return False

    def check_worker_status(self) -> None:
        """Check and display worker status."""
        print("\n" + "=" * 50)
        print("   STATUT DU WORKER DE TEMPÉRATURE")
        print("=" * 50)
        print()

        if not self.api:
            print("✗ API non initialisée")
            return

        # Check if worker task exists
        has_worker = self.api._temperature_task is not None
        print(f"Worker créé: {'✓ Oui' if has_worker else '✗ Non'}")

        if has_worker:
            is_done = self.api._temperature_task.done()
            print(f"Worker actif: {'✓ Oui (en cours)' if not is_done else '✗ Non (arrêté)'}")

        # Check queue
        has_queue = self.api.queue_target_temperature is not None
        print(f"Queue créée: {'✓ Oui' if has_queue else '✗ Non'}")

        if has_queue:
            queue_size = self.api.queue_target_temperature.qsize()
            print(f"Éléments en queue: {queue_size}")

            if queue_size > 0:
                print("\n⚠️  Requêtes en attente:")
                print("  (Les requêtes seront traitées par le worker)")
                print(f"  - {queue_size} requête(s) en queue")
                print(f"  - Le worker traite 1 requête tous les 5 secondes")
                print(f"  - ETA: ~{queue_size * 5} secondes")
            else:
                print("\n✓ Queue vide (aucune requête en attente)")
        else:
            print("Queue: Non créée (aucune requête envoyée)")

        print()
        print("ℹ️  Comment ça fonctionne:")
        print("  1. Quand vous changez la température → Requête mise en queue")
        print("  2. Worker récupère la requête → Appelle l'API")
        print("  3. API met à jour → Nouvelle donnée")
        print("  4. Prochaine lecture → Données à jour affichées")
        print()

    def show_menu(self) -> None:
        """Display main menu."""
        print("\n" + "=" * 50)
        print("   MENU DE TEST ALDES API")
        print("=" * 50)
        print("1. S'authentifier")
        print("2. Récupérer les données du compte")
        print("3. Changer la température d'un thermostat")
        print("4. Changer le mode air")
        print("5. Changer le mode eau chaude")
        print("6. Afficher les informations du compte")
        print("7. Vérifier le statut du worker")
        print("8. Quitter")
        print("=" * 50)

    async def run(self) -> None:
        """Run the interactive menu."""
        print("\n" + "=" * 50)
        print("  INTÉGRATION ALDES - TEST AUTONOME")
        print("=" * 50)
        print("Bienvenue! Cet outil vous permet de tester l'API Aldes")
        print("sans Home Assistant.")

        try:
            while True:
                self.show_menu()
                choice = await self.ainput("Votre choix (1-8): ")
                choice = choice.strip()

                if choice == "1":
                    await self.authenticate()
                elif choice == "2":
                    await self.fetch_data()
                elif choice == "3":
                    await self.change_room_temperature()
                elif choice == "4":
                    await self.change_air_mode()
                elif choice == "5":
                    await self.change_hot_water_mode()
                elif choice == "6":
                    if self.data:
                        self._display_account_info()
                    else:
                        print("\n✗ Veuillez d'abord récupérer les données.")
                elif choice == "7":
                    self.check_worker_status()
                elif choice == "8":
                    print("\n✓ Au revoir!")
                    break
                else:
                    print("✗ Choix invalide.")
        except KeyboardInterrupt:
            print("\n\n✓ Test interrompu par l'utilisateur.")
        finally:
            await self.cleanup()


async def main() -> None:
    """Main entry point."""
    menu = AldesTestMenu()
    await menu.run()


if __name__ == "__main__":
    asyncio.run(main())
