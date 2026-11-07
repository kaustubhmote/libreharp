"""Optional local action counts. No document text, paths, or timestamps."""

from .store import Store

ACTIONS = ("Applied", "Ignored", "Remembered word")


class Statistics(Store):
    def __init__(self, directory):
        super().__init__(directory)
        self.path = self.directory / "statistics.json"
        self.lock_path = self.directory / "statistics.lock"

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or set(data) - set(ACTIONS):
            raise ValueError("Invalid statistics data.")
        if any(
            not isinstance(rules, dict)
            or any(
                not isinstance(rule, str) or type(count) is not int or count < 1
                for rule, count in rules.items()
            )
            for rules in data.values()
        ):
            raise ValueError("Invalid statistics counts.")
        return data

    def read(self):
        with self.lock:
            return super().read() if self.path.exists() else {}

    def record(self, action, rule):
        def change(data):
            counts = data.setdefault(action, {})
            counts[rule] = counts.get(rule, 0) + 1

        self.update(change)

    def clear(self):
        self.update(dict.clear)
