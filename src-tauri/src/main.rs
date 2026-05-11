#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use ai_social_auto_upload_lib::{check_webview2, create_data_dirs, get_data_dir};
use tauri::{Manager, WindowEvent};

fn main() {
    env_logger::init();
    log::info!("Starting AI Social Auto Upload desktop app");

    // Check WebView2
    if let Err(e) = check_webview2() {
        eprintln!("ERROR: {}", e);
        eprintln!("Please install Microsoft Edge WebView2 Runtime from:");
        eprintln!("https://developer.microsoft.com/en-us/microsoft-edge/webview2/");
        std::process::exit(1);
    }

    // Get paths
    let exe_dir = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();

    let data_dir = get_data_dir();
    log::info!("Data directory: {:?}", data_dir);

    // Create data directories
    if let Err(e) = create_data_dirs(&data_dir) {
        eprintln!("ERROR: Could not create data directory: {}", e);
        std::process::exit(1);
    }

    // Find available port
    let port = find_available_port(5409);
    log::info!("Using backend port: {}", port);

    // Python path and backend path
    let python_path = exe_dir.join("python").join("python.exe");
    let backend_path = exe_dir.join("backend").join("app.py");

    // Spawn Python backend
    let mut child = match Command::new(&python_path)
        .arg(&backend_path)
        .env("SAU_PORT", port.to_string())
        .env("SAU_DATA_DIR", data_dir.to_str().unwrap())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("ERROR: Failed to start backend: {}", e);
            eprintln!("Python path: {:?}", python_path);
            eprintln!("Backend path: {:?}", backend_path);
            std::process::exit(1);
        }
    };

    // Log backend output in background
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                log::info!("[backend] {}", line);
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                eprintln!("[backend error] {}", line);
            }
        });
    }

    // Wait for backend to be ready
    let backend_url = format!("http://localhost:{}", port);
    log::info!("Waiting for backend at {}", backend_url);
    let max_wait = 30;
    for i in 0..max_wait {
        if std::net::TcpStream::connect(&backend_url[..]).is_ok() {
            log::info!("Backend ready after {} seconds", i);
            break;
        }
        if i == max_wait - 1 {
            eprintln!("ERROR: Backend did not start within {} seconds", max_wait);
            child.kill().ok();
            std::process::exit(1);
        }
        std::thread::sleep(std::time::Duration::from_secs(1));
    }

    // Create Tauri app
    tauri::Builder::default()
        .setup(move |app| {
            let window = app.get_webview_window("main").unwrap();
            window.eval(&format!(
                "window.location.replace('{}')",
                backend_url
            )).unwrap();
            Ok(())
        })
        .on_window_event(move |_window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                log::info!("Window closed, shutting down");
                child.kill().ok();
                std::process::exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn find_available_port(start: u16) -> u16 {
    use std::net::TcpListener;
    for port in start..start + 100 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    start
}