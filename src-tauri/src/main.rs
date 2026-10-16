// Без чёрного окна консоли в release-сборке.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod legacy;

#[tauri::command]
fn import_legacy_settings() -> legacy::LegacySettings {
    legacy::read()
}

/// Windows: короткая пауза на каждом изменении размера даёт WebView2 успеть
/// перерисоваться, и содержимое меньше отстаёт от края окна при растягивании
/// (обходной путь из tauri-apps/tauri#6322).
#[cfg(windows)]
fn smooth_resize(event: &tauri::WindowEvent) {
    if let tauri::WindowEvent::Resized(_) = event {
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
}

#[cfg(not(windows))]
fn smooth_resize(_event: &tauri::WindowEvent) {}

fn main() {
    tauri::Builder::default()
        .on_window_event(|_window, event| smooth_resize(event))
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .invoke_handler(tauri::generate_handler![import_legacy_settings])
        .run(tauri::generate_context!())
        .expect("не удалось запустить приложение");
}
