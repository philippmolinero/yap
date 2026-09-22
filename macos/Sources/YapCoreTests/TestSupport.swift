import Foundation

/// Minimal test harness: the Command Line Tools toolchain ships neither
/// swift-testing nor XCTest, so Yap runs its suite through this runner.
/// Usage: `swift run YapCoreTests` (exit code 0 = all green).

struct TestFailure: Error, CustomStringConvertible {
    let description: String
}

func expect(
    _ condition: Bool,
    _ message: String = "expectation failed",
    file: StaticString = #fileID,
    line: UInt = #line
) throws {
    guard condition else {
        throw TestFailure(description: "\(file):\(line): \(message)")
    }
}

func require<T>(
    _ value: T?,
    _ message: String = "unexpected nil",
    file: StaticString = #fileID,
    line: UInt = #line
) throws -> T {
    guard let value else {
        throw TestFailure(description: "\(file):\(line): \(message)")
    }
    return value
}

struct TestCase {
    let name: String
    let run: () async throws -> Void
}

final class Suite {
    let name: String
    private(set) var cases: [TestCase] = []

    init(_ name: String) {
        self.name = name
    }

    func test(_ name: String, _ run: @escaping () async throws -> Void) {
        cases.append(TestCase(name: name, run: run))
    }
}

@main
enum TestRunner {
    static func main() async {
        // Keep test logs and files away from the user's real config directory.
        let isolated = NSTemporaryDirectory() + "yap-test-config-\(UUID().uuidString)"
        setenv("YAP_CONFIG_DIR", isolated, 1)

        var passed = 0
        var failed = 0
        for suite in allSuites() {
            print("== \(suite.name)")
            for testCase in suite.cases {
                do {
                    try await testCase.run()
                    print("   PASS  \(testCase.name)")
                    passed += 1
                } catch {
                    print("   FAIL  \(testCase.name)")
                    print("         \(error)")
                    failed += 1
                }
            }
        }
        print("")
        print("\(passed) passed, \(failed) failed")
        try? FileManager.default.removeItem(atPath: isolated)
        exit(failed == 0 ? 0 : 1)
    }
}

func allSuites() -> [Suite] {
    [
        tomlSuite(),
        configSuite(),
        secretsSuite(),
        wavSuite(),
        historySuite(),
        metricsSuite(),
        languageSuite(),
        geminiMessageSuite(),
        pipelineSuite(),
    ]
}
