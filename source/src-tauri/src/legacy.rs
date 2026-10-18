//! Чтение настроек старой (Python/PyQt5) версии из реестра Windows.
//!
//! QSettings("Vaponok", "LogisticsPlanner") и QSettings("Vaponok",
//! "WarehouseTimer") хранят значения в HKCU\Software\Vaponok\<приложение>:
//! строки и bool — REG_SZ ("true"/"false"), int — REG_DWORD/REG_QWORD.
//! Строки, начинающиеся с '@', Qt экранирует вторым '@'; служебные значения
//! вида "@ByteArray(...)" (геометрия окна) пропускаются.

use std::collections::BTreeMap;

#[derive(serde::Serialize, Default)]
pub struct LegacySettings {
    pub splitter: BTreeMap<String, String>,
    pub timers: BTreeMap<String, String>,
}

pub fn read() -> LegacySettings {
    LegacySettings {
        splitter: read_app("LogisticsPlanner"),
        timers: read_app("WarehouseTimer"),
    }
}

#[cfg(windows)]
fn read_app(app: &str) -> BTreeMap<String, String> {
    use winreg::enums::{RegType, HKEY_CURRENT_USER};
    use winreg::RegKey;

    let mut out = BTreeMap::new();
    let path = format!("Software\\Vaponok\\{app}");
    let key = match RegKey::predef(HKEY_CURRENT_USER).open_subkey(&path) {
        Ok(k) => k,
        Err(_) => return out,
    };
    for item in key.enum_values() {
        let Ok((name, value)) = item else { continue };
        let text = match value.vtype {
            RegType::REG_SZ | RegType::REG_EXPAND_SZ => match key.get_value::<String, _>(&name) {
                Ok(s) => s,
                Err(_) => continue,
            },
            RegType::REG_DWORD => match key.get_value::<u32, _>(&name) {
                Ok(n) => (n as i32).to_string(),
                Err(_) => continue,
            },
            RegType::REG_QWORD => match key.get_value::<u64, _>(&name) {
                Ok(n) => (n as i64).to_string(),
                Err(_) => continue,
            },
            _ => continue,
        };
        if let Some(v) = unescape_qt(text) {
            out.insert(name, v);
        }
    }
    out
}

#[cfg(not(windows))]
fn read_app(_app: &str) -> BTreeMap<String, String> {
    BTreeMap::new()
}

/// "@@текст" -> "@текст"; "@ByteArray(...)", "@Invalid()" и т.п. -> None.
#[cfg_attr(not(windows), allow(dead_code))]
fn unescape_qt(s: String) -> Option<String> {
    if let Some(rest) = s.strip_prefix("@@") {
        return Some(format!("@{rest}"));
    }
    if s.starts_with('@') {
        return None;
    }
    Some(s)
}

#[cfg(test)]
mod tests {
    use super::unescape_qt;

    #[test]
    fn qt_escaping() {
        assert_eq!(unescape_qt("@@Полк".into()), Some("@Полк".into()));
        assert_eq!(unescape_qt("@ByteArray(abc)".into()), None);
        assert_eq!(unescape_qt("@Invalid()".into()), None);
        assert_eq!(unescape_qt("true".into()), Some("true".into()));
    }
}
