"""
Test reporting utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TestResult:
    """Test result data."""

    name: str
    status: str  # "passed", "failed", "skipped", "error"
    duration: float
    message: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TestSuiteResult:
    """Test suite result data."""

    name: str
    tests: List[TestResult]
    total: int
    passed: int
    failed: int
    skipped: int
    duration: float


@dataclass
class PipelineReport:
    """Complete pipeline test report."""

    timestamp: str
    total_tests: int
    total_passed: int
    total_failed: int
    total_skipped: int
    total_duration: float
    suites: List[TestSuiteResult]
    coverage: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None


class TestReporter:
    """Test results reporter."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize test reporter.

        Args:
            output_dir: Directory for report files
        """
        self.output_dir = (
            output_dir or Path(__file__).parent.parent.parent / "test_reports"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.suites: List[TestSuiteResult] = []
        self.current_suite: Optional[TestSuiteResult] = None
        self.start_time: Optional[float] = None

    def start_pipeline(self) -> None:
        """Start pipeline reporting."""
        self.start_time = time.time()
        self.suites = []
        self.current_suite = None

    def start_suite(self, name: str) -> None:
        """Start test suite.

        Args:
            name: Suite name
        """
        if self.current_suite is not None:
            self.end_suite()

        self.current_suite = TestSuiteResult(
            name=name,
            tests=[],
            total=0,
            passed=0,
            failed=0,
            skipped=0,
            duration=0.0,
        )

    def add_test_result(
        self,
        name: str,
        status: str,
        duration: float,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Add test result.

        Args:
            name: Test name
            status: Test status
            duration: Test duration in seconds
            message: Optional message
            error: Optional error message
        """
        if self.current_suite is None:
            self.start_suite("default")
        if self.current_suite is None:  # pragma: no cover - defensive typing guard
            raise RuntimeError("Failed to initialize reporting suite")

        result = TestResult(
            name=name,
            status=status,
            duration=duration,
            message=message,
            error=error,
        )

        self.current_suite.tests.append(result)
        self.current_suite.total += 1

        if status == "passed":
            self.current_suite.passed += 1
        elif status == "failed" or status == "error":
            self.current_suite.failed += 1
        elif status == "skipped":
            self.current_suite.skipped += 1

        self.current_suite.duration += duration

    def end_suite(self) -> None:
        """End current test suite."""
        if self.current_suite is not None:
            self.suites.append(self.current_suite)
            self.current_suite = None

    def end_pipeline(self) -> PipelineReport:
        """End pipeline reporting.

        Returns:
            Pipeline report
        """
        if self.current_suite is not None:
            self.end_suite()

        total_duration = time.time() - self.start_time if self.start_time else 0.0

        total_tests = sum(suite.total for suite in self.suites)
        total_passed = sum(suite.passed for suite in self.suites)
        total_failed = sum(suite.failed for suite in self.suites)
        total_skipped = sum(suite.skipped for suite in self.suites)

        report = PipelineReport(
            timestamp=datetime.now().isoformat(),
            total_tests=total_tests,
            total_passed=total_passed,
            total_failed=total_failed,
            total_skipped=total_skipped,
            total_duration=total_duration,
            suites=self.suites,
        )

        return report

    def save_report(self, report: PipelineReport, format: str = "json") -> Path:
        """Save test report to file.

        Args:
            report: Pipeline report
            format: Report format ("json" or "html")

        Returns:
            Path to saved report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            report_path = self.output_dir / f"test_report_{timestamp}.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(asdict(report), f, indent=2)
            return report_path

        elif format == "html":
            report_path = self.output_dir / f"test_report_{timestamp}.html"
            html_content = self._generate_html_report(report)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return report_path

        else:
            raise ValueError(f"Unknown report format: {format}")

    def _generate_html_report(self, report: PipelineReport) -> str:
        """Generate HTML report.

        Args:
            report: Pipeline report

        Returns:
            HTML content
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test Pipeline Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .suite {{ margin: 20px 0; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }}
        .test {{ margin: 10px 0; padding: 10px; background: #f9f9f9; border-radius: 3px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .skipped {{ color: orange; }}
        .error {{ color: red; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Test Pipeline Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Timestamp:</strong> {report.timestamp}</p>
        <p><strong>Total Tests:</strong> {report.total_tests}</p>
        <p><strong>Passed:</strong> <span class="passed">{report.total_passed}</span></p>
        <p><strong>Failed:</strong> <span class="failed">{report.total_failed}</span></p>
        <p><strong>Skipped:</strong> <span class="skipped">{report.total_skipped}</span></p>
        <p><strong>Duration:</strong> {report.total_duration:.2f}s</p>
    </div>
"""

        for suite in report.suites:
            html += f"""
    <div class="suite">
        <h3>{suite.name}</h3>
        <p>Total: {suite.total}, Passed: <span class="passed">{suite.passed}</span>, 
           Failed: <span class="failed">{suite.failed}</span>, 
           Skipped: <span class="skipped">{suite.skipped}</span>, 
           Duration: {suite.duration:.2f}s</p>
"""

            for test in suite.tests:
                status_class = test.status
                html += f"""
        <div class="test">
            <strong class="{status_class}">{test.name}</strong> - 
            <span class="{status_class}">{test.status}</span> ({test.duration:.3f}s)
"""
                if test.message:
                    html += f"<p>{test.message}</p>"
                if test.error:
                    html += f'<p class="error">Error: {test.error}</p>'
                html += "</div>"

            html += "</div>"

        html += """
</body>
</html>
"""

        return html

    def print_summary(self, report: PipelineReport) -> None:
        """Print test summary to console.

        Args:
            report: Pipeline report
        """
        print("\n" + "=" * 80)
        print("TEST PIPELINE SUMMARY")
        print("=" * 80)
        print(f"Timestamp: {report.timestamp}")
        print(f"Total Tests: {report.total_tests}")
        print(f"Passed: {report.total_passed}")
        print(f"Failed: {report.total_failed}")
        print(f"Skipped: {report.total_skipped}")
        print(f"Duration: {report.total_duration:.2f}s")
        print("=" * 80)

        for suite in report.suites:
            print(f"\n{suite.name}:")
            print(
                f"  Total: {suite.total}, Passed: {suite.passed}, "
                f"Failed: {suite.failed}, Skipped: {suite.skipped}, "
                f"Duration: {suite.duration:.2f}s"
            )

        print("=" * 80 + "\n")
