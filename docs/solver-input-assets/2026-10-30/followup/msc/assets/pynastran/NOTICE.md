# PyNastran reference source additions

Upstream: https://github.com/SteveDoyle2/pyNastran

Revision: f51e9ffa74222f93750618d4766e59f2f96751c3 (same pin as the PR10 source excerpts).

The six files under `pyNastran/bdf/` are upstream source excerpts retained for reading the typed card creation, native field ordering, references/defaults, and formatting path. BSD-3-Clause LICENSE.md is included. They are not a standalone package, newly implemented writer, or executed code.

The MSC contact module explicitly lists BCBODY1, BCONECT, BCONPRP, and BCTABL1 as todo at this revision. Do not infer full modern SOL400 generation support from its BCBODY implementation or from raw-text preservation.

Source paths:

- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/bdf_interface/add_card.py
- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/cards/elements/solid.py
- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/cards/properties/solid.py
- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/cards/constraints.py
- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/cards/contact/msc.py
- https://github.com/SteveDoyle2/pyNastran/blob/f51e9ffa74222f93750618d4766e59f2f96751c3/pyNastran/bdf/cards/contact/contact_common.py
