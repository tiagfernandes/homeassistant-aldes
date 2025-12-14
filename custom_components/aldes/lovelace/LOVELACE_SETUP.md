# Carte planning Aldes – mise en place

## Prérequis
- Intégration Aldes installée et fonctionnelle.
- Les entités planning exposent `planning_data` en liste de chaînes type `00C`.
- La ressource de la carte est servie sur `/aldes_planning_card.js`.

## 1) Déclarer la ressource Lovelace
Dans **Paramètres → Tableaux de bord → Ressources** (ou en YAML brut) :
```yaml
resources:
  - url: /aldes_planning_card.js
    type: module
```

## 2) Ajouter la carte (config minimale)
Sans préciser d’entités, la carte auto-découvre les plannings via `sensor.aldes_*_planning_(heating|cooling)_prog_[a-d]`.
```yaml
type: custom:aldes-planning-card
```

## 3) Ajouter la carte avec entités explicites
Spécifiez les sensors, tri A→B→C→D.
```yaml
type: custom:aldes-planning-card
entities:
  - sensor.aldes_XXXX_planning_heating_prog_a
  - sensor.aldes_XXXX_planning_heating_prog_b
  - sensor.aldes_XXXX_planning_cooling_prog_c
  - sensor.aldes_XXXX_planning_cooling_prog_d
```

## 4) Fonctionnement
- Sélecteur pour choisir le programme (A/B/C/D) affiché et envoyé.
- Grille interactive : clic bascule chaque case B↔C (chauffage : Confort/Eco, clim : Confort/Off).
- Envoi via `aldes.set_week_planning`, mode déduit de l’entité (prog_a/b/c/d), avec indicateur de chargement, confirmation/erreur, timeout 12s.
- Cellules sans lettres (couleur seule) + légende des modes.

## 5) Données exposées
- `state` : nombre d’items (ex: "168 items").
- `planning_data` : liste de chaînes (ex: `00C`, `01C`, ...).
- `planning_json` : JSON formaté équivalent.
- `item_count` : nombre d’items.

## 6) Astuces
- Rechargez la page ou videz le cache si la ressource change.

## 7) Dépannage
- **"Custom element doesn't exist"** : vérifier la ressource, recharger HA, vider le cache.
- **"Entity not found"** : vérifier l'ID exact (`sensor.aldes_*_planning_*`).
- **Pas de données** : intégration active, appareil connecté, entité `available`.
