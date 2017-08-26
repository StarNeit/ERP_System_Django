__author__ = 'bank'

import time
import documents as d
from intramanee.common.errors import BadParameterError
from intramanee.common.codes import models
from intramanee.stock.documents import MaterialMaster
from datetime import datetime
import random, math, copy


class DesignMockTemplate(object):

    master_model = ("TST021XXXXMNNNNN", "pc")

    default_materials = [
        ("stock-TST011S999UTD130", "pc"),
        ("stock-TST011S999UTD490", "pc"),
        ("stock-TST011S999U18YSE", "pc"),
        ("stock-TST011S999U18WSE", "pc"),

        ("stock-TST011S999LSG420", "pc"),
        ("stock-TST011S999LSR500", "pc"),
        ("stock-TST011S999COPPER", "g"),
        ("stock-TST011S999LAG108", "g"),
        ("stock-TST011S999LOTTGR", "pc"),
        ("stock-TST011S999UGN109", "pc"),
        ("stock-TST011S999UFX127", "pc"),
        ("stock-TST011SILVUTD130", "pc"),
        ("stock-TST011SILVUTD490", "pc"),
        ("stock-TST011SILVU18YSE", "pc"),
        ("stock-TST011SILVU18WSE", "pc"),

        ("stock-TST011SILVLSG420", "g"),
        ("stock-TST011SILVLSR500", "pc"),
        ("stock-TST011SILVCOPPER", "pc"),
        ("stock-TST011SILVLAG108", "pc"),
        ("stock-TST011SILVLOTTGR", "pc"),
        ("stock-TST011SILVUGN109", "pc"),
        ("stock-TST011SILVUFX127", "pc"),
        ("stock-TST011S900UTD130", "pc"),
        ("stock-TST011S900UTD490", "g"),
        ("stock-TST011S900U18YSE", "g"),
        ("stock-TST011S900U18WSE", "pc"),

        ("stock-TST011S900LSG420", "pc"),
        ("stock-TST011S900LSR500", "pc"),
        ("stock-TST011S900COPPER", "pc"),
        ("stock-TST011S900LAG108", "pc"),
        ("stock-TST011S900LOTTGR", "pc"),
        ("stock-TST011S900UGN109", "g"),
        ("stock-TST011S900UFX127", "g"),
        ("stock-TST011SXXXUTD130", "pc"),
        ("stock-TST011SXXXUTD490", "pc"),
        ("stock-TST011SXXXU18YSE", "pc"),
        ("stock-TST011SXXXU18WSE", "pc"),

        ("stock-TST011SXXXLSG420", "pc"),
        ("stock-TST011SXXXLSR500", "pc"),
        ("stock-TST011SXXXCOPPER", "g"),
        ("stock-TST011SXXXLAG108", "g"),
        ("stock-TST011SXXXLOTTGR", "pc"),
        ("stock-TST011SXXXUGN109", "pc"),
        ("stock-TST011SXXXUFX127", "pc"),
        ("stock-TST011G999UTD130", "pc"),
        ("stock-TST011G999UTD490", "pc"),
        ("stock-TST011G999U18YSE", "pc"),
        ("stock-TST011G999U18WSE", "pc"),

        ("stock-TST011G999LSG420", "g"),
        ("stock-TST011G999LSR500", "pc"),
        ("stock-TST011G999COPPER", "pc"),
        ("stock-TST011G999LAG108", "pc"),
        ("stock-TST011G999LOTTGR", "pc"),
        ("stock-TST011G999UGN109", "pc"),
        ("stock-TST011G999UFX127", "pc"),
        ("stock-TST011GY18UTD130", "pc"),
        ("stock-TST011GY18UTD490", "g"),
        ("stock-TST011GY18U18YSE", "g"),
        ("stock-TST011GY18U18WSE", "pc"),

        ("stock-TST011GY18LSG420", "pc"),
        ("stock-TST011GY18LSR500", "pc"),
        ("stock-TST011GY18COPPER", "pc"),
        ("stock-TST011GY18LAG108", "pc"),
        ("stock-TST011GY18LOTTGR", "pc"),
        ("stock-TST011GY18UGN109", "g"),
        ("stock-TST011GY18UFX127", "g"),
        ("stock-TST011GY14UTD130", "pc"),
        ("stock-TST011GY14UTD490", "pc"),
        ("stock-TST011GY14U18YSE", "pc"),
        ("stock-TST011GY14U18WSE", "pc"),

        ("stock-TST011GY14LSG420", "pc"),
        ("stock-TST011GY14LSR500", "pc"),
        ("stock-TST011GY14COPPER", "g"),
        ("stock-TST011GY14LAG108", "g"),
        ("stock-TST011GY14LOTTGR", "pc"),
        ("stock-TST011GY14UGN109", "pc"),
        ("stock-TST011GY14UFX127", "pc"),
        ("stock-TST011GY10UTD130", "pc"),
        ("stock-TST011GY10UTD490", "pc"),
        ("stock-TST011GY10U18YSE", "pc"),
        ("stock-TST011GY10U18WSE", "pc"),

        ("stock-TST011GY10LSG420", "g"),
        ("stock-TST011GY10LSR500", "pc"),
        ("stock-TST011GY10COPPER", "pc"),
        ("stock-TST011GY10LAG108", "pc"),
        ("stock-TST011GY10LOTTGR", "pc"),
        ("stock-TST011GY10UGN109", "pc"),
        ("stock-TST011GY10UFX127", "pc"),
        ("stock-TST011GY09UTD130", "pc"),
        ("stock-TST011GY09UTD490", "g"),
        ("stock-TST011GY09U18YSE", "g"),
        ("stock-TST011GY09U18WSE", "pc"),

        ("stock-TST011GY09LSG420", "pc"),
        ("stock-TST011GY09LSR500", "pc"),
        ("stock-TST011GY09COPPER", "pc"),
        ("stock-TST011GY09LAG108", "pc"),
        ("stock-TST011GY09LOTTGR", "pc"),
        ("stock-TST011GY09UGN109", "g"),
        ("stock-TST011GY09UFX127", "g"),
        ("stock-TST011GYXXUTD130", "pc"),
        ("stock-TST011GYXXUTD490", "pc"),
        ("stock-TST011GYXXU18YSE", "pc"),
        ("stock-TST011GYXXU18WSE", "pc"),

        ("stock-TST011GYXXLSG420", "pc"),
        ("stock-TST011GYXXLSR500", "pc"),
        ("stock-TST011GYXXCOPPER", "g"),
        ("stock-TST011GYXXLAG108", "g"),
        ("stock-TST011GYXXLOTTGR", "pc"),
        ("stock-TST011GYXXUGN109", "pc"),
        ("stock-TST011GYXXUFX127", "pc"),
        ("stock-TST011GW18UTD130", "pc"),
        ("stock-TST011GW18UTD490", "pc"),
        ("stock-TST011GW18U18YSE", "pc"),
        ("stock-TST011GW18U18WSE", "pc"),

        ("stock-TST011GW18LSG420", "g"),
        ("stock-TST011GW18LSR500", "pc"),
        ("stock-TST011GW18COPPER", "pc"),
        ("stock-TST011GW18LAG108", "pc"),
        ("stock-TST011GW18LOTTGR", "pc"),
        ("stock-TST011GW18UGN109", "pc"),
        ("stock-TST011GW18UFX127", "pc"),
        ("stock-TST011GW14UTD130", "pc"),
        ("stock-TST011GW14UTD490", "g"),
        ("stock-TST011GW14U18YSE", "g"),
        ("stock-TST011GW14U18WSE", "pc"),

        ("stock-TST011GW14LSG420", "pc"),
        ("stock-TST011GW14LSR500", "pc"),
        ("stock-TST011GW14COPPER", "pc"),
        ("stock-TST011GW14LAG108", "pc"),
        ("stock-TST011GW14LOTTGR", "pc"),
        ("stock-TST011GW14UGN109", "g"),
        ("stock-TST011GW14UFX127", "g"),
        ("stock-TST011GW10UTD130", "pc"),
        ("stock-TST011GW10UTD490", "pc"),
        ("stock-TST011GW10U18YSE", "pc"),
        ("stock-TST011GW10U18WSE", "pc"),

        ("stock-TST011GW10LSG420", "pc"),
        ("stock-TST011GW10LSR500", "pc"),
        ("stock-TST011GW10COPPER", "g"),
        ("stock-TST011GW10LAG108", "g"),
        ("stock-TST011GW10LOTTGR", "pc"),
        ("stock-TST011GW10UGN109", "pc"),
        ("stock-TST011GW10UFX127", "pc"),
        ("stock-TST011GW09UTD130", "pc"),
        ("stock-TST011GW09UTD490", "pc"),
        ("stock-TST011GW09U18YSE", "pc"),
        ("stock-TST011GW09U18WSE", "pc"),

        ("stock-TST011GW09LSG420", "g"),
        ("stock-TST011GW09LSR500", "pc"),
        ("stock-TST011GW09COPPER", "pc"),
        ("stock-TST011GW09LAG108", "pc"),
        ("stock-TST011GW09LOTTGR", "pc"),
        ("stock-TST011GW09UGN109", "pc"),
        ("stock-TST011GW09UFX127", "pc"),
        ("stock-TST011GWXXUTD130", "pc"),
        ("stock-TST011GWXXUTD490", "g"),
        ("stock-TST011GWXXU18YSE", "g"),
        ("stock-TST011GWXXU18WSE", "pc"),

        ("stock-TST011GWXXLSG420", "pc"),
        ("stock-TST011GWXXLSR500", "pc"),
        ("stock-TST011GWXXCOPPER", "pc"),
        ("stock-TST011GWXXLAG108", "pc"),
        ("stock-TST011GWXXLOTTGR", "pc"),
        ("stock-TST011GWXXUGN109", "g"),
        ("stock-TST011GWXXUFX127", "g"),
        ("stock-TST011GR18UTD130", "pc"),
        ("stock-TST011GR18UTD490", "pc"),
        ("stock-TST011GR18U18YSE", "pc"),
        ("stock-TST011GR18U18WSE", "pc"),

        ("stock-TST011GR18LSG420", "pc"),
        ("stock-TST011GR18LSR500", "pc"),
        ("stock-TST011GR18COPPER", "g"),
        ("stock-TST011GR18LAG108", "g"),
        ("stock-TST011GR18LOTTGR", "pc"),
        ("stock-TST011GR18UGN109", "pc"),
        ("stock-TST011GR18UFX127", "pc"),
        ("stock-TST011GR14UTD130", "pc"),
        ("stock-TST011GR14UTD490", "pc"),
        ("stock-TST011GR14U18YSE", "pc"),
        ("stock-TST011GR14U18WSE", "pc"),

        ("stock-TST011GR14LSG420", "g"),
        ("stock-TST011GR14LSR500", "pc"),
        ("stock-TST011GR14COPPER", "pc"),
        ("stock-TST011GR14LAG108", "pc"),
        ("stock-TST011GR14LOTTGR", "pc"),
        ("stock-TST011GR14UGN109", "pc"),
        ("stock-TST011GR14UFX127", "pc"),
        ("stock-TST011GR10UTD130", "pc"),
        ("stock-TST011GR10UTD490", "g"),
        ("stock-TST011GR10U18YSE", "g"),
        ("stock-TST011GR10U18WSE", "pc"),

        ("stock-TST011GR10LSG420", "pc"),
        ("stock-TST011GR10LSR500", "pc"),
        ("stock-TST011GR10COPPER", "pc"),
        ("stock-TST011GR10LAG108", "pc"),
        ("stock-TST011GR10LOTTGR", "pc"),
        ("stock-TST011GR10UGN109", "g"),
        ("stock-TST011GR10UFX127", "g"),
        ("stock-TST011GR09UTD130", "pc"),
        ("stock-TST011GR09UTD490", "pc"),
        ("stock-TST011GR09U18YSE", "pc"),
        ("stock-TST011GR09U18WSE", "pc"),

        ("stock-TST011GR09LSG420", "pc"),
        ("stock-TST011GR09LSR500", "pc"),
        ("stock-TST011GR09COPPER", "g"),
        ("stock-TST011GR09LAG108", "g"),
        ("stock-TST011GR09LOTTGR", "pc"),
        ("stock-TST011GR09UGN109", "pc"),
        ("stock-TST011GR09UFX127", "pc"),
        ("stock-TST011GRXXUTD130", "pc"),
        ("stock-TST011GRXXUTD490", "pc"),
        ("stock-TST011GRXXU18YSE", "pc"),
        ("stock-TST011GRXXU18WSE", "pc"),

        ("stock-TST011GRXXLSG420", "g"),
        ("stock-TST011GRXXLSR500", "pc"),
        ("stock-TST011GRXXCOPPER", "pc"),
        ("stock-TST011GRXXLAG108", "pc"),
        ("stock-TST011GRXXLOTTGR", "pc"),
        ("stock-TST011GRXXUGN109", "pc"),
        ("stock-TST011GRXXUFX127", "pc"),
        ("stock-TST011BNZYUTD130", "pc"),
        ("stock-TST011BNZYUTD490", "g"),
        ("stock-TST011BNZYU18YSE", "g"),
        ("stock-TST011BNZYU18WSE", "pc"),

        ("stock-TST011BNZYLSG420", "pc"),
        ("stock-TST011BNZYLSR500", "pc"),
        ("stock-TST011BNZYCOPPER", "pc"),
        ("stock-TST011BNZYLAG108", "pc"),
        ("stock-TST011BNZYLOTTGR", "pc"),
        ("stock-TST011BNZYUGN109", "g"),
        ("stock-TST011BNZYUFX127", "g"),
        ("stock-TST011BMTLUTD130", "pc"),
        ("stock-TST011BMTLUTD490", "pc"),
        ("stock-TST011BMTLU18YSE", "pc"),
        ("stock-TST011BMTLU18WSE", "pc"),

        ("stock-TST011BMTLLSG420", "pc"),
        ("stock-TST011BMTLLSR500", "pc"),
        ("stock-TST011BMTLCOPPER", "g"),
        ("stock-TST011BMTLLAG108", "g"),
        ("stock-TST011BMTLLOTTGR", "pc"),
        ("stock-TST011BMTLUGN109", "pc"),
        ("stock-TST011BMTLUFX127", "pc"),
        ("stock-TST011WOODUTD130", "pc"),
        ("stock-TST011WOODUTD490", "pc"),
        ("stock-TST011WOODU18YSE", "pc"),
        ("stock-TST011WOODU18WSE", "pc"),

        ("stock-TST011WOODLSG420", "g"),
        ("stock-TST011WOODLSR500", "pc"),
        ("stock-TST011WOODCOPPER", "pc"),
        ("stock-TST011WOODLAG108", "pc"),
        ("stock-TST011WOODLOTTGR", "pc"),
        ("stock-TST011WOODUGN109", "pc"),
        ("stock-TST011WOODUFX127", "pc"),
        ("stock-TST011STANUTD130", "pc"),
        ("stock-TST011STANUTD490", "g"),
        ("stock-TST011STANU18YSE", "g"),
        ("stock-TST011STANU18WSE", "pc"),

        ("stock-TST011STANLSG420", "pc"),
        ("stock-TST011STANLSR500", "pc"),
        ("stock-TST011STANCOPPER", "pc"),
        ("stock-TST011STANLAG108", "pc"),
        ("stock-TST011STANLOTTGR", "pc"),
        ("stock-TST011STANUGN109", "g"),
        ("stock-TST011STANUFX127", "pc"),
        ("stock-TST011NIKLUTD130", "pc"),
        ("stock-TST011NIKLUTD490", "pc"),
        ("stock-TST011NIKLU18YSE", "pc"),
        ("stock-TST011NIKLU18WSE", "pc"),

        ("stock-TST011NIKLLSG420", "pc"),
        ("stock-TST011NIKLLSR500", "g"),
        ("stock-TST011NIKLCOPPER", "g"),
        ("stock-TST011NIKLLAG108", "pc"),
        ("stock-TST011NIKLLOTTGR", "pc"),
        ("stock-TST011NIKLUGN109", "pc"),
        ("stock-TST011NIKLUFX127", "pc"),
    ]

    staging_duration = [
        3, 5
    ]

    master_model_template = [
        {
            "master_modeling": [
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4113,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [],
                    "materials": [],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        10,
                        12
                    ],
                    "id": "1000"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4152,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [
                        "1000"
                    ],
                    "materials": [],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        5,
                        7
                    ],
                    "id": "1001"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 5331,
                    "markup": 0.0000000000000000,
                    "is_configurable": False,
                    "source": [
                        "1001"
                    ],
                    "materials": [],
                    "staging_duration": [
                        staging_duration[0]
                    ],
                    "duration": [
                        1440
                    ],
                    "id": "1002"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4142,
                    "markup": 0.0000000000000000,
                    "is_configurable": False,
                    "source": [
                        "1002"
                    ],
                    "materials": [
                        {
                            "cost": 20,
                            "code": "raw_material",
                            "is_configurable": False,
                            "quantity": [
                                5
                            ],
                            "counter": "g"
                        }
                    ],
                    "staging_duration": [
                        staging_duration[0]
                    ],
                    "duration": [
                        5
                    ],
                    "id": "1003"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4143,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [
                        "1003"
                    ],
                    "materials": [
                        {
                            "cost": 0,
                            "code": "master_model",
                            "is_configurable": True,
                            "quantity": [
                                -1,
                                -2
                            ],
                            "counter": "pc"
                        }
                    ],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        5,
                        7
                    ],
                    "id": "1004"
                }
            ]
        },
        {
            "master_modeling": [
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4112,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [],
                    "materials": [],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        5,
                        7
                    ],
                    "id": "1000"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4152,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [
                        "1000"
                    ],
                    "materials": [],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        4,
                        7
                    ],
                    "id": "1001"
                },
                {
                    "labor_cost": 0.0000000000000000,
                    "process": 4143,
                    "markup": 0.0000000000000000,
                    "is_configurable": True,
                    "source": [
                        "1001"
                    ],
                    "materials": [
                        {
                            "cost": 0,
                            "code": "master_model",
                            "is_configurable": True,
                            "quantity": [
                                -1,
                                -2
                            ],
                            "counter": "pc"
                        }
                    ],
                    "staging_duration": [
                        staging_duration[0],
                        staging_duration[1]
                    ],
                    "duration": [
                        3,
                        5
                    ],
                    "id": "1002"
                }
            ]
        }
    ]

    templates = [
        {
            "process": {
                "sample_creation": [
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5331,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [],
                        "materials": [
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 0,
                                "code": "master_model",
                                "is_configurable": True,
                                "quantity": [
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 0,
                                "code": "master_model",
                                "is_configurable": True,
                                "quantity": [
                                    -1,
                                    -2
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            1440,
                            1440
                        ],
                        "id": "1"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5381,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [
                            "1"
                        ],
                        "materials": [
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            5,
                            7
                        ],
                        "id": "2"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5392,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [
                            "2"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            6,
                            7
                        ],
                        "id": "3"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5341,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [
                            "3"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            3,
                            4
                        ],
                        "id": "4"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5351,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [
                            "4"
                        ],
                        "materials": [
                            {
                                "cost": 0,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [
                                    18,
                                    19
                                ],
                                "counter": "inch"
                            },
                            {
                                "cost": 0,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [
                                    7,
                                    8
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 0,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [
                                    3,
                                    4
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            8,
                            9
                        ],
                        "id": "5"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 4142,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "5"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            5
                        ],
                        "id": "6"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5391,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "6"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            2
                        ],
                        "id": "7"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5401,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "7"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            5
                        ],
                        "id": "8"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5381,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [
                            "8"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            2,
                            3
                        ],
                        "id": "9"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5433,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "9"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            10
                        ],
                        "id": "10"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5421,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "10"
                        ],
                        "materials": [
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            },
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": False,
                                "quantity": [
                                    1
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            6
                        ],
                        "id": "11"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5432,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "11"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            10
                        ],
                        "id": "12"
                    },
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5351,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [
                            "12"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [
                            10
                        ],
                        "id": "13"
                    },
                ],
            },
        },
        {
            "process": {
                "sample_creation": [ 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5331,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [],
                        "materials": [ 
                            {
                                "cost": 10,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 10,
                                "code": "master_model",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 0,
                                "code": "master_model",
                                "is_configurable": True,
                                "quantity": [ 
                                    -1,
                                    -2
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [
                            1440,
                            1440
                        ],
                        "id": "1"
                    }, 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5381,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [ 
                            "1"
                        ],
                        "materials": [ 
                            {
                                "cost": 20,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [ 
                            5,
                            7
                        ],
                        "id": "2"
                    }, 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5341,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [ 
                            "2"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [ 
                            6,
                            7
                        ],
                        "id": "3"
                    }, 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5401,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [ 
                            "3"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [ 
                            2,
                            3
                        ],
                        "id": "4"
                    }, 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5421,
                        "markup": 0.0000000000000000,
                        "is_configurable": True,
                        "source": [ 
                            "4"
                        ],
                        "materials": [ 
                            {
                                "cost": 1,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 2,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 3,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 4,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 5,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 6,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }, 
                            {
                                "cost": 7,
                                "code": "raw_material",
                                "is_configurable": True,
                                "quantity": [ 
                                    1,
                                    2
                                ],
                                "counter": "pc"
                            }
                        ],
                        "staging_duration": [
                            staging_duration[1],
                            staging_duration[1]
                        ],
                        "duration": [ 
                            5,
                            7
                        ],
                        "id": "5"
                    }, 
                    {
                        "labor_cost": 0.0000000000000000,
                        "process": 5432,
                        "markup": 0.0000000000000000,
                        "is_configurable": False,
                        "source": [ 
                            "5"
                        ],
                        "materials": [],
                        "staging_duration": [
                            staging_duration[1]
                        ],
                        "duration": [ 
                            3
                        ],
                        "id": "6"
                    }
                ],
            },
        }
    ]

    base_size = map(lambda a: models.LOV.ensure_exist(models.LOV.RANDD_SIZE, a), [
        'S', 'XXXL'
    ])

    base_template = {
        "design_number": "0003",
        "code": "code",
        "misc": None,
        "size": base_size,
        "sales_manifest": {
            "due_date": "due",
            "quantity": 1
        },
        "rev_id": 1,
        "plating": "plating",
        "finish": "finish",
        "style": "style",
        "customer": "cust-TST",
        "stone": "stone",
        "collection_name": "default",
        "counter": "pc",
        "metal": "metal",
        "stamping": [],
        "rev_unique_id" : "rev_unique_id",
    }

    metals = [
        "S999",
        "SILV",
        "S900",
        "SXXX",
        "G999",
        "GY18",
        "GY14",
        "GY10",
        "GY09",
        "GYXX",
        "GW18",
        "GW14",
        "GW10",
        "GW09",
        "GWXX",
        "GR18",
        "GR14",
        "GR10",
        "GR09",
        "GRXX",
        "BNZY",
        "BMTL",
        "WOOD",
        "STAN",
        "NIKL",
        "CPPR",
        "ALOY",
        "TITN",
        "STEE",
        "PALL",
        "CHEM",
        "S608",
        "G683",
        "WAXX",
        "SILI"
    ]

    finished_pattern = "TST180XXXXNL2NNNNHP18"

    @classmethod
    def get_numbers(cls):
        return {'template_no': len(cls.templates),
                'raw_materials': len(cls.default_materials),
                }

    @classmethod
    def get_randomized_index(cls):
        all_index = [i for i in range(0, len(cls.default_materials)-1)]
        random.shuffle(all_index)
        return all_index

    @classmethod
    def get_randomized_template(cls):
        return random.randint(0, len(cls.templates)-1)

    @classmethod
    def get_master_model(cls, _number):
        # number = math.floor(_number / 3) if _number > 3 else _number
        number = _number
        running = 0
        hit = 0
        result = []
        for m in cls.metals:
            if hit > number-1:
                break
            while True:
                if hit > number-1:
                    break

                code = cls.master_model[0][:].replace("XXXX", m).replace("NNNNN", ("00000"+str(running))[-5:])
                if not MaterialMaster.manager.find(0, 0, {'code': "stock-"+code}):
                    result.append((code, "pc"))
                    hit += 1

                running += 1
                if running % 10000 == 0:
                    break

        return result

    @classmethod
    def get_finished_code(cls, number):
        running = 0
        hit = 0
        result = []
        for m in cls.metals:
            if hit > number-1:
                break
            while True:
                if hit > number-1:
                    break

                code = cls.finished_pattern[:].replace("XXXX", m).replace("NNNN", ("0000"+str(running))[-4:])
                if not d.DesignUID.lookup(code):
                    result.append(code)
                    hit += 1

                running += 1
                if running % 10000 == 0:
                    break

        return result

    @classmethod
    def get_template(cls, verbose=True, **kwargs):

        def message(v, m):
            if v:
                print m

        tn = kwargs.pop('template_no', 0)
        raw_materials = kwargs.pop('raw_materials', cls.default_materials)
        raw_index = kwargs.pop('raw_index', None)
        mn = kwargs.pop('master_template', 0)
        master_model = kwargs.pop('master_model', cls.master_model)
        include_master = kwargs.pop('include_master', False)

        template = copy.deepcopy(cls.templates[tn])
        template.update(cls.base_template)
        if include_master:
            template['process'].update(copy.deepcopy(cls.master_model_template[mn]))
        template['design_number'] = kwargs.pop('design_number', None)
        if not template['design_number']:
            raise BadParameterError("Require design number")

        template['code'] = kwargs.pop('code', None)
        if not template['code']:
            raise BadParameterError("Require finished material code")

        template['rev_unique_id'] = kwargs.pop('rev_unique_id', None)
        if not template['rev_unique_id']:
            raise BadParameterError("Require rev_unique_id")

        template['plating'] = [kwargs.pop('plating', "plating-18")]
        template['finish'] = [kwargs.pop('finish', "finish-HP")]
        template['style'] = [kwargs.pop('style', "style-NL")]
        template['stone'] = [kwargs.pop('stone', "stone-2")]
        template['metal'] = [kwargs.pop('metal', "metal-SILV")]
        template['misc'] = kwargs.pop('misc', "Mock Data")
        template['sales_manifest']['due_date'] = time.mktime(kwargs.pop('due_date', datetime.today().timetuple()))

        index = kwargs.pop('index', 0)
        raw_len = len(raw_materials)
        for k, v in template['process'].iteritems():
            for process in v:
                for mat in process['materials']:
                    if mat['code'] == "raw_material":
                        ind = index % raw_len
                        mat['code'] = raw_materials[ind][0] if not raw_index else raw_materials[raw_index[ind]][0]
                        mat['counter'] = raw_materials[ind][1] if not raw_index else raw_materials[raw_index[ind]][1]
                        index += 1
                    if mat['code'] == "master_model":
                        mat['code'] = master_model[0]
                        mat['counter'] = master_model[1]

        return template
