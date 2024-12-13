[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Aldes integration for Home Assistant

This integration allows Home Assistant to interact with an Aldes product through the cloud. You must have an AldesConnect box connected to the device, set up and working in the mobile app.

## Supported products

| **Fonctionality**                                                                                                        | **T.One® AIR** | **T.One® AquaAIR** |
| ------------------------------------------------------------------------------------------------------------------------ | -------------- | ------------------ |
| **Air Mode** (Off, Heat Comfort, Heat Eco, Heat Prog A, Heat Prog B, Cool Comfort, Cool Boost, Cool Prog A, Cool Prog B) | ✔️              | ✔️                  |
| **Water Mode** (Off, On, Boost)                                                                                          | ❌              | ✔️                  |
| **Connectivity**                                                                                                         | ✔️              | ✔️                  |
| **Main Room Tempeature**                                                                                                 | ✔️              | ✔️                  |
| **Water Tank Quantity** (0%, 25%, 50%, 75%, 100%)                                                                        | ❌              | ✔️                  |
| **Temperature sensor for each room**                                                                                     | ✔️              | ✔️                  |
| **Climate entity for each room**                                                                                         | ✔️              | ✔️                  |


## Installation

In HACS, add the custom repository https://github.com/tiagfernandes/homeassistant-aldes and select the Integration category.

## Configuration

The username and password asked during the configuration are the same that you use for the Aldes mobile app.

## Credits

- [API doc](https://community.jeedom.com/t/aldes-connect-api/57068)
- [API auth & call examples](https://github.com/aalmazanarbs/hassio_aldes)
- [More API doc](https://community.jeedom.com/t/aldes-t-one-api-php/94269)
- [Integration blueprint](https://github.com/custom-components/integration_blueprint)

## See also

- https://github.com/Fredzxda/homeassistant-aldes for EASYHOME PureAir Compact CONNECT
