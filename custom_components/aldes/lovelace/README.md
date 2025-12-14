# Aldes Planning Card - Installation Guide

## Installation

### 1. Install the custom card

Add the following to your Home Assistant `configuration.yaml`:

```yaml
frontend:
  extra_module_url:
    - /local/aldes-planning-card.js
```

### 2. Copy the card file

Copy `lovelace/aldes-planning-card.js` to your Home Assistant `www` folder:

```bash
config/www/aldes-planning-card.js
```

### 3. Add the card to your dashboard

In your Lovelace dashboard, add a custom card with the following YAML:

```yaml
type: custom:aldes-planning-card
entity: text.aldes_planning_weekly  # Replace with your planning entity ID
```

## Features

- **Visual Grid**: 7 days × 24 hours grid showing the weekly planning
- **Color-coded Modes**: Each planning mode has a unique color for easy identification
- **Responsive**: Works on desktop, tablet, and mobile devices
- **Read-only Display**: Shows the current planning stored in the text entity

## Planning Entity

The planning is stored as JSON in the `text.aldes_planning_weekly` entity.

Example format:
```json
[
  {"command": "00C"},
  {"command": "01C"},
  ...
  {"command": "N6C"}
]
```

## Mode Colors

| Mode | Color | Meaning |
|------|-------|---------|
| A | Red | Off |
| B | Orange | Heat Comfort |
| C | Blue | Heat Eco |
| D | Yellow | Heat Prog A |
| E | Dark Orange | Heat Prog B |
| F | Green | Cool Comfort |
| G | Dark Green | Cool Boost |
| H | Teal | Cool Prog A |
| I | Dark Blue | Cool Prog B |

## Future Enhancements

- [ ] Interactive mode switching (click to change)
- [ ] Drag and drop planning
- [ ] Import/export planning
- [ ] Planning templates
- [ ] Scheduled updates

## Notes

Currently, the card displays the planning in read-only mode. To edit the planning, you can manually modify the JSON in the text entity through the Home Assistant UI.
