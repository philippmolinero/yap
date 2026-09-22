import Foundation

/// URL session wrapper with the retry policy Yap uses for provider calls:
/// three attempts on transport errors, 429, and 5xx; everything else fails fast.
public struct RetryingHTTPClient: Sendable {
    public var session: URLSession
    public var attempts: Int
    public var retryDelays: [TimeInterval]

    public init(
        session: URLSession = .shared,
        attempts: Int = 3,
        retryDelays: [TimeInterval] = [0.5, 1.0]
    ) {
        self.session = session
        self.attempts = max(1, attempts)
        self.retryDelays = retryDelays.isEmpty ? [0.5] : retryDelays
    }

    public func send(_ request: URLRequest) async throws -> Data {
        var lastError: TranscriptionError = .transport("request failed")
        for attempt in 0..<attempts {
            if attempt > 0 {
                let delay = retryDelays[min(attempt - 1, retryDelays.count - 1)]
                try? await Task.sleep(for: .seconds(delay))
            }
            do {
                let (data, response) = try await session.data(for: request)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                if (200..<300).contains(status) {
                    return data
                }
                let error = TranscriptionError.http(status)
                if !error.isRetryable {
                    throw error
                }
                lastError = error
                YapLog.warning("Request got HTTP \(status) (attempt \(attempt + 1)/\(attempts))")
            } catch let error as TranscriptionError {
                throw error
            } catch is CancellationError {
                throw TranscriptionError.transport("cancelled")
            } catch {
                lastError = .transport(error.localizedDescription)
                YapLog.warning(
                    "Request failed: \(error.localizedDescription) (attempt \(attempt + 1)/\(attempts))"
                )
            }
        }
        throw lastError
    }
}
