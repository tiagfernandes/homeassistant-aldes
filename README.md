[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Intégration Aldes T.One via AldesConnect pour Home Assistant

Cette intégration permet d'ajouter le produit Aldes T.One à Home Assistant via le cloud. Vous devez disposer de la box AldesConnect, connectée à l'appareil, configurée et fonctionnelle dans l'application mobile AldesConnect.

## Fonctionnalités prises en charge

| **Fonctionnalité**                                                                                                                                                                                                             | **T.One® AIR** | **T.One® AquaAIR** |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------: | :----------------: |
| **Mode Air** <br>- Éteint<br>- Chauffage Comfort<br>- Chauffage Eco<br>- Chauffage Prog A<br>- Chauffage Prog B<br>- Rafraîchissement Comfort<br>- Rafraîchissement Boost<br>- Rafraîchissement A<br>- Rafraîchissement Prog B |       ✔️        |         ✔️          |
| **Mode Eau chaude** <br>- Éteint<br>- Allumé<br>- Boost                                                                                                                                                                        |       ❌        |         ✔️          |
| **Connectivité**                                                                                                                                                                                                               |       ✔️        |         ✔️          |
| **Température de la pièce principale**                                                                                                                                                                                         |       ✔️        |         ✔️          |
| **Quantité d'eau chaude disponible**                                                                                                                                                                                           |       ❌        |         ✔️          |
| **Capteur de température pour chaque pièce**                                                                                                                                                                                   |       ✔️        |         ✔️          |
| **Entité thermostat pour chaque pièce**                                                                                                                                                                                        |       ✔️        |         ✔️          |
| **Composition du foyer**                                                                                                                                                                                                       |       ❌        |         ✔️          |
| **Cycle Antilegionelle**                                                                                                                                                                                                       |       ❌        |         ✔️          |
| **Configuration des tarifs électriques**                                                                                                                                                                                       |       ✔️        |         ✔️          |
| **Mode vacances**                                                                                                                                                                                                              |       ✔️        |         ✔️          |
| **Statistiques et coûts**                                                                                                                                                                                                      |       ✔️        |         ✔️          |
| **Surveillance du filtre**                                                                                                                                                                                                     |       ✔️        |         ✔️          |
| **Carte de planning**                                                                                                                                                                                                          |       ✔️        |         ✔️          |

## Installation

Dans HACS, ajoutez le dépôt personnalisé <https://github.com/tiagfernandes/homeassistant-aldes> et sélectionnez la catégorie Intégration.

## Configuration

Le nom d'utilisateur et le mot de passe demandés lors de la configuration sont les mêmes que ceux que vous utilisez pour l'application mobile Aldes Connect.

### Carte de planning interactive (optionnel)

Pour utiliser la carte de planning avec grille éditable :

1. **Déclarer la ressource Lovelace**
   Allez dans **Paramètres → Tableaux de bord → Ressources** et ajoutez :
   ```yaml
   url: /aldes_planning_card.js
   type: module
   ```

2. **Ajouter la carte à votre tableau de bord**
   Configuration minimale (auto-découverte des plannings) :
   ```yaml
   type: custom:aldes-planning-card
   ```

   Ou avec entités explicites :
   ```yaml
   type: custom:aldes-planning-card
   entities:
     - sensor.aldes_XXXX_planning_heating_prog_a
     - sensor.aldes_XXXX_planning_heating_prog_b
     - sensor.aldes_XXXX_planning_cooling_prog_c
     - sensor.aldes_XXXX_planning_cooling_prog_d
   ```

3. **Fonctionnalités**
   - Sélecteur de programme (A/B/C/D)
   - Grille interactive : clic pour basculer Confort ↔ Eco (chauffage) ou Confort ↔ Off (climatisation)
   - Envoi automatique via service `aldes.set_week_planning`
   - Indicateur de chargement et confirmation/erreur
   - Légende des modes avec code couleur

📖 [Documentation complète de la carte](custom_components/aldes/lovelace/LOVELACE_SETUP.md)

## Crédits

- [Base du projet](https://github.com/guix77/homeassistant-aldes)
- [API doc](https://community.jeedom.com/t/aldes-connect-api/57068)
- [Swagger Aldes](https://aldesiotsuite-aldeswebapi.azurewebsites.net/swagger/index.html?urls.primaryName=V5)
- [Exemples d'authentification et d'appel API](https://github.com/aalmazanarbs/hassio_aldes)
- [Plus de documentation API](https://community.jeedom.com/t/aldes-t-one-api-php/94269)
- [Blueprint d'intégration](https://github.com/custom-components/integration_blueprint)

## Voir aussi

- <https://github.com/guix77/esphome-aldes-tone> : Connexion du produit T.One avec ESPHome
- <https://github.com/Fredzxda/homeassistant-aldes> : EASYHOME PureAir Compact CONNECT

<a href="https://www.buymeacoffee.com/tiagfernandes" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;"></a>
