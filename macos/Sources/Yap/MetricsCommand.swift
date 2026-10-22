import Foundation
import YapCore

/// `yap --metrics [file]`: summarize release-to-paste timings already on disk.
/// Prints no transcript text. Does not take the single-instance lock, so it
/// can run while the menu-bar app is dictating.
enum MetricsCommand {
    static func run(arguments: [String]) -> Int32 {
        let url = metricsURL(from: arguments)
        do {
            let load = try MetricsLog.load(from: url)
            print(MetricsReport.build(from: load).render(path: url.path))
            return 0
        } catch {
            FileHandle.standardError.write(Data("could not read \(url.path)\n".utf8))
            return 1
        }
    }

    /// The argument after `--metrics` is an optional JSONL path. Anything that
    /// looks like another flag is ignored so the default file is used.
    static func metricsURL(from arguments: [String]) -> URL {
        guard let flag = arguments.firstIndex(of: "--metrics") else {
            return AppConfig.metricsURL
        }
        let next = arguments.index(after: flag)
        guard next < arguments.endIndex else { return AppConfig.metricsURL }
        let candidate = arguments[next]
        guard !candidate.hasPrefix("-"), !candidate.isEmpty else { return AppConfig.metricsURL }
        return URL(fileURLWithPath: candidate)
    }
}
