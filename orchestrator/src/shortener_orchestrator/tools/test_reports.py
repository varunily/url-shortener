from pathlib import Path
import xml.etree.ElementTree as ET

def parse_reports(workspace: Path):
    counts = {"unit_tests": 0, "integration_tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for folder, key in [("surefire-reports", "unit_tests"), ("failsafe-reports", "integration_tests")]:
        for report in (workspace / "target" / folder).glob("TEST-*.xml"):
            if report.stat().st_size > 5_000_000:
                raise ValueError("Oversized test report")
            root = ET.parse(report).getroot()
            counts[key] += int(root.get("tests", "0"))
            for field in ["failures", "errors", "skipped"]:
                counts[field] += int(root.get(field, "0"))
    return counts
