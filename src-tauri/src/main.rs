// Без чёрного окна консоли в release-сборке.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod legacy;

#[tauri::command]
fn import_legacy_settings() -> legacy::LegacySettings {
    legacy::read()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .invoke_handler(tauri::generate_handler![import_legacy_settings])
        .run(tauri::generate_context!())
        .expect("не удалось запустить приложение");
}
