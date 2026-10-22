import ApplicationServices
import Foundation
import YapCore

/// Reads names and code from the focused field for one dictation turn.
///
/// Accessibility is already required to paste. A slow target app is cut off
/// after a short timeout so key-down still starts dictation. Password fields
/// are skipped. The text is not logged and is not written to disk.
enum FocusedContextReader {
    /// How long an Accessibility query may block. Past this, the turn proceeds
    /// with the saved vocabulary only.
    private static let timeout: Float = 0.3

    static func terms() -> [String] {
        guard AXIsProcessTrusted() else { return [] }
        let system = AXUIElementCreateSystemWide()
        AXUIElementSetMessagingTimeout(system, timeout)
        guard let focused = copyElement(system, kAXFocusedUIElementAttribute as CFString) else { return [] }
        AXUIElementSetMessagingTimeout(focused, timeout)
        if isSecure(focused) { return [] }

        let focusedText = copyString(focused, kAXValueAttribute as CFString) ?? ""
        return TurnContext.terms(focusedText: focusedText, windowTitle: windowTitle(of: focused))
    }

    private static func isSecure(_ element: AXUIElement) -> Bool {
        let role = copyString(element, kAXRoleAttribute as CFString)
        let subrole = copyString(element, kAXSubroleAttribute as CFString)
        // Password fields are AXTextField with subrole kAXSecureTextFieldSubrole.
        if subrole == kAXSecureTextFieldSubrole as String { return true }
        return TurnContext.isSecureField(role: role, subrole: subrole)
    }

    private static func windowTitle(of element: AXUIElement) -> String {
        if let window = copyElement(element, kAXWindowAttribute as CFString) {
            AXUIElementSetMessagingTimeout(window, timeout)
            if let title = copyString(window, kAXTitleAttribute as CFString), !title.isEmpty {
                return title
            }
        }
        return copyString(element, kAXTitleAttribute as CFString) ?? ""
    }

    private static func copyElement(_ element: AXUIElement, _ attribute: CFString) -> AXUIElement? {
        guard let value = copyValue(element, attribute) else { return nil }
        guard CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
        return (value as! AXUIElement)
    }

    private static func copyString(_ element: AXUIElement, _ attribute: CFString) -> String? {
        copyValue(element, attribute) as? String
    }

    private static func copyValue(_ element: AXUIElement, _ attribute: CFString) -> CFTypeRef? {
        var value: CFTypeRef?
        let error = AXUIElementCopyAttributeValue(element, attribute, &value)
        guard error == .success else { return nil }
        return value
    }
}
