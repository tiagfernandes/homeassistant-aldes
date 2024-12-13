[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Integration Aldes T.One via AldesConnect pour Home Assistant

Cette intégration permet d'intégrer le produit Aldes T.One à Home Assistant via le cloud. Vous devez disposer de la box AldesConnect, connectée à l'appareil, configurée et fonctionnelle dans l'application mobile AldesConnect.

## Fonctionnalités prises en charge

| **Fonctionnalité**                                                                                                                                                                                                             | **T.One® AIR** | **T.One® AquaAIR** |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------: | :----------------: |
| **Mode Air** <br>- Éteind<br>- Chauffage Comfort<br>- Chauffage Eco<br>- Chauffage Prog A<br>- Chauffage Prog B<br>- Rafraîchissement Comfort<br>- Rafraîchissement Boost<br>- Rafraîchissement A<br>- Rafraîchissement Prog B |       ✔️        |         ✔️          |
| **Mode Eau chaude** <br>- Éteind<br>- Allumé<br> - Boost                                                                                                                                                                       |       ❌        |         ✔️          |
| **Connectivité**                                                                                                                                                                                                               |       ✔️        |         ✔️          |
| **Température de la pièce principale**                                                                                                                                                                                         |       ✔️        |         ✔️          |
| **Quantité d'eau chaude disponible**                                                                                                                                                                                           |       ❌        |         ✔️          |
| **Capteur de température pour chaque pièce**                                                                                                                                                                                   |       ✔️        |         ✔️          |
| **Entité thermostat pour chaque pièce**                                                                                                                                                                                        |       ✔️        |         ✔️          |




## Installation

Dans HACS, ajoutez le dépôt personnalisé https://github.com/tiagfernandes/homeassistant-aldes et sélectionnez la catégorie Intégration.

## Configuration

Le nom d'utilisateur et le mot de passe demandés lors de la configuration sont les mêmes que ceux que vous utilisez pour l'application mobile Aldes Connect.

## Crédits

- [Base du projet](https://github.com/guix77/homeassistant-aldes)
- [API doc](https://community.jeedom.com/t/aldes-connect-api/57068)
- [API auth & call examples](https://github.com/aalmazanarbs/hassio_aldes)
- [More API doc](https://community.jeedom.com/t/aldes-t-one-api-php/94269)
- [Integration blueprint](https://github.com/custom-components/integration_blueprint)

## See also
- https://github.com/guix77/esphome-aldes-tone Connection du produit T.One avec ESPHome
- https://github.com/Fredzxda/homeassistant-aldes for EASYHOME PureAir Compact CONNECT
