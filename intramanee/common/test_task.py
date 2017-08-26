from unittest import TestCase
from task import ExtendExpander, ForkExpander, SchematicDummy, Task


class TestTask(TestCase):

    def _to_schematic_sequence(self, context, echo=False):
        if echo:
            for ctx in context:
                print ctx
        return map(lambda s: s.task_code, context)

    def test_detail_expansion(self):
        # build data for testing
        context = [
            SchematicDummy("1", 4143),
            SchematicDummy("2", 4171, ["1"]),
            SchematicDummy("3", 5331, ["2"]),
            SchematicDummy("4", 5421, ["3"]),
            SchematicDummy("5", 5422, ["4"]),
            SchematicDummy("6", 5422, ["5"]),
        ]

        ExtendExpander.populate(context)
        ForkExpander.expand(context)
        o = self._to_schematic_sequence(context)
        self.assertEqual([4143, 4171, 5331, 5411, 5421, 5422, 5422, 5467], o)
        ExtendExpander.expand(context, is_production=False)
        o = self._to_schematic_sequence(context)
        self.assertEqual([4143, 5461, 4171, 5261, 5271, 5291, 5331, 5462, 5391, 5311, 5411, 5421, 5422, 5422, 5467, 5412], o)

    def test_complex_expansion(self):
        context = [
            SchematicDummy("1", 5341),
            SchematicDummy("2", 5331),
            SchematicDummy("3", 5361, ["1", "2"]),
            SchematicDummy("4", 5401, ["3"]),
            SchematicDummy("5", 5421, ["4"]),
            SchematicDummy("6", 5422, ["5"]),
        ]

        Task.expand(context, is_production=False)
        o = self._to_schematic_sequence(context)
        self.assertEqual([5341, 5271, 5291, 5331, 5462, 5391, 5311, 5361, 5463,
                          5401, 5466, 5411, 5421, 5422, 5467, 5412], o)

        context = [
            SchematicDummy("1", 5341),
            SchematicDummy("2", 5331),
            SchematicDummy("3", 5361, ["1", "2"]),
            SchematicDummy("4", 5401, ["3"]),
            SchematicDummy("5", 5421, ["4"]),
            SchematicDummy("6", 5422, ["5"]),
        ]

        Task.expand(context, is_production=True)
        o = self._to_schematic_sequence(context)
        self.assertEqual([5341, 5271, 5291, 5331, 5462, 5391, 5311, 5361, 5463, 5401,
                          5466, 5411, 5421, 5422, 5467, 5412, 5468, 5471], o)
