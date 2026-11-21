"""
Driver Scanner & Update Checker Engine
Scans connected Windows hardware devices via pnputil and checks for
the latest manufacturer drivers via the Microsoft Update Catalog and OEM portals.
100% silent execution without CMD or PowerShell windows popping up.
Subsystem-aware matching to ensure OEM-specific drivers (Dell, HP, Lenovo) match perfectly.
Filters out Microsoft inbox system stubs to prevent cross-vendor false positives.
"""

import os
import re
import winreg
import subprocess
import catalog
import urllib.request
import urllib.parse
from datetime import datetime

CREATE_NO_WINDOW = 0x08000000

def get_silent_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si

# Microsoft Windows inbox drivers that should be managed by Windows Kernel/Update
MICROSOFT_INBOX_INFS = {
    "machine.inf",
    "usbvideo.inf",
    "audioendpoint.inf",
    "kdnic.inf",
    "spaceport.inf",
    "ksfilter.inf",
    "microsoft_bluetooth_hfp.inf",
    "microsoft_bluetooth_a2dp_src.inf"
}

VENDOR_PCI_MAP = {
    "8086": "Intel",
    "8087": "Intel",
    "10DE": "NVIDIA",
    "1002": "AMD",
    "10EC": "Realtek",
    "0BDA": "Realtek",
    "14E4": "Broadcom",
    "17CB": "Qualcomm",
    "14C3": "MediaTek",
    "1B21": "ASMedia",
    "046D": "Logitech",
    "045E": "Microsoft",
    "1028": "Dell",
    "103C": "HP",
    "17AA": "Lenovo",
    "1043": "ASUS",
    "144D": "Samsung",
}

# OEM-specific overrides, matched on a hardware-ID substring.
# Kept as data so per-OEM quirks stop scattering through the check logic.
OEM_HWID_RULES = [
    {
        "oem": "dell",
        "match": "DEV_5916",
        "only_if_version": "27.20.100.9664",
        "latest_version": "27.20.100.9664",
        "latest_date": "06/01/2021",
        "force_up_to_date": True,
        "note": "Dell validated driver is current (v27.20.100.9664). To install generic Intel DCH drivers, use Intel DSA.",
    },
    {
        "oem": "dell",
        "match": "10EC&DEV_0256",
        "download_url": "https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2026/03/5808e972-5160-4430-a579-48b8c7322503_2df41a34eaa30bddd4430c787718b3054c198312.cab",
        "latest_version": "6.0.9960.1",
        "latest_date": "03/03/2026",
        "note": "Official Dell Realtek High Definition Audio Driver (ALC3234).",
    },
]

VENDOR_PORTALS = {
    "Intel": "https://www.intel.com/content/www/us/en/support/detect.html",
    "NVIDIA": "https://www.nvidia.com/Download/index.aspx",
    "AMD": "https://www.amd.com/en/support",
    "Realtek": "https://www.realtek.com/",
    "Dell": "https://www.dell.com/support/home/en-us/quicklink/drivers",
    "HP": "https://support.hp.com/us-en/drivers",
    "Lenovo": "https://pcsupport.lenovo.com/",
    "Logitech": "https://support.logi.com/",
    "Broadcom": "https://www.broadcom.com/support/download-search",
    "Samsung": "https://semiconductor.samsung.com/consumer-storage/support/tools/",
}

def _read_smbios_serial():
    """Serial number from the raw SMBIOS table via GetSystemFirmwareTable.

    Costs about 0.05 ms. Used because many OEM boards (this HP included) do
    not publish the serial anywhere in the registry.
    """
    try:
        import ctypes
        from ctypes import wintypes

        rsmb = 0x52534D42  # "RSMB"
        kernel32 = ctypes.windll.kernel32
        kernel32.GetSystemFirmwareTable.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        kernel32.GetSystemFirmwareTable.restype = wintypes.UINT

        size = kernel32.GetSystemFirmwareTable(rsmb, 0, None, 0)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not kernel32.GetSystemFirmwareTable(rsmb, 0, buf, size):
            return ""
        data = buf.raw[:size]
    except Exception:
        return ""

    offset = 8  # RSMB header: 4 bytes + DWORD table length
    while offset + 4 <= len(data):
        struct_type = data[offset]
        struct_len = data[offset + 1]
        if struct_len < 4 or offset + struct_len > len(data):
            break
        if struct_type == 127:  # end-of-table
            break

        if struct_type == 1 and struct_len > 7:  # System Information
            index = data[offset + 7]  # Serial Number string index
            if index:
                strings = []
                pos = offset + struct_len
                while pos < len(data) and data[pos] != 0:
                    end = data.find(b"\x00", pos)
                    if end < 0:
                        break
                    strings.append(data[pos:end].decode("latin-1", "ignore"))
                    pos = end + 1
                if 1 <= index <= len(strings):
                    return strings[index - 1].strip()

        pos = offset + struct_len
        while pos + 1 < len(data) and not (data[pos] == 0 and data[pos + 1] == 0):
            pos += 1
        offset = pos + 2

    return ""


_SYSTEM_MANUFACTURER = None


def system_manufacturer():
    """Cached manufacturer string, used to keep OEM-specific rules honest."""
    global _SYSTEM_MANUFACTURER
    if _SYSTEM_MANUFACTURER is None:
        try:
            _SYSTEM_MANUFACTURER = (get_system_info().get("manufacturer") or "").lower()
        except Exception:
            _SYSTEM_MANUFACTURER = ""
    return _SYSTEM_MANUFACTURER


def _read_serial_number():
    """BIOS serial straight from the registry (sub-millisecond).

    PowerShell costs ~300 ms to start, so it is only a fallback for machines
    that do not publish the serial in the BIOS key.
    """
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
        try:
            for value_name in ("SystemSerialNumber", "BaseBoardSerialNumber"):
                try:
                    serial = str(winreg.QueryValueEx(key, value_name)[0]).strip()
                except Exception:
                    continue
                if serial:
                    return serial
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass

    serial = _read_smbios_serial()
    if serial:
        return serial

    try:
        cmd = 'Get-CimInstance Win32_BIOS | Select-Object -ExpandProperty SerialNumber'
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass

    return ""


def get_system_info():
    info = {
        "manufacturer": "Unknown",
        "model": "Unknown",
        "serial_number": "",
        "service_tag": "",
        "os_version": "Windows",
        "oem_url": "",
        "oem_name": "OEM Support"
    }

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
        try:
            info["manufacturer"] = winreg.QueryValueEx(key, "SystemManufacturer")[0].strip()
        except FileNotFoundError:
            pass
        try:
            info["model"] = winreg.QueryValueEx(key, "SystemProductName")[0].strip()
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        prod_name, _ = winreg.QueryValueEx(key, "ProductName")
        build_num, _ = winreg.QueryValueEx(key, "CurrentBuild")
        display_version = ""
        try:
            display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
        except FileNotFoundError:
            pass
        if display_version:
            info["os_version"] = f"Windows {display_version} (Build {build_num})"
        else:
            info["os_version"] = f"{prod_name} (Build {build_num})"
        winreg.CloseKey(key)
    except Exception:
        pass

    serial = _read_serial_number()
    if serial:
        info["serial_number"] = serial
        if "dell" in info["manufacturer"].lower():
            info["service_tag"] = serial

    mfg_lower = info["manufacturer"].lower()
    if "dell" in mfg_lower:
        info["oem_name"] = "Dell Official Support"
        if info["service_tag"]:
            info["oem_url"] = f"https://www.dell.com/support/home/en-us/product-support/servicetag/{info['service_tag']}/drivers"
        elif info["model"]:
            clean_model = info["model"].lower().replace(" ", "-")
            info["oem_url"] = f"https://www.dell.com/support/home/en-us/product-support/product/{clean_model}/drivers"
        else:
            info["oem_url"] = "https://www.dell.com/support/home/en-us/quicklink/drivers"
    elif "hp" in mfg_lower or "hewlett" in mfg_lower:
        info["oem_name"] = "HP Official Support"
        info["oem_url"] = "https://support.hp.com/us-en/drivers"
    elif "lenovo" in mfg_lower:
        info["oem_name"] = "Lenovo Official Support"
        info["oem_url"] = "https://pcsupport.lenovo.com/"
    elif "asus" in mfg_lower:
        info["oem_name"] = "ASUS Official Support"
        info["oem_url"] = "https://www.asus.com/support/Download-Center/"
    elif "acer" in mfg_lower:
        info["oem_name"] = "Acer Official Support"
        info["oem_url"] = "https://www.acer.com/us-en/support/drivers-and-manuals"
    elif "msi" in mfg_lower:
        info["oem_name"] = "MSI Official Support"
        info["oem_url"] = "https://www.msi.com/support"
    else:
        info["oem_name"] = f"{info['manufacturer']} Drivers"
        info["oem_url"] = f"https://www.google.com/search?q={urllib.parse.quote(info['manufacturer'] + ' ' + info['model'] + ' official drivers')}"

    return info


LAST_SCAN_ERROR = ""


def windows_build_number():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        try:
            return int(winreg.QueryValueEx(key, "CurrentBuildNumber")[0])
        finally:
            winreg.CloseKey(key)
    except Exception:
        return 0


def get_architecture():
    """'x64', 'x86' or 'ARM64' — the OS architecture, not the app's."""
    arch = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or "").upper()
    if arch == "ARM64":
        return "ARM64"
    if arch in ("AMD64", "X86_64", "IA64"):
        return "x64"
    if arch == "X86":
        return "x86"
    try:
        import platform
        machine = platform.machine().upper()
        if "ARM" in machine:
            return "ARM64"
        return "x64" if "64" in machine else "x86"
    except Exception:
        return "x64"


def _new_device_record(instance_id="", description="", class_name="", manufacturer="", status="Healthy",
                       driver_name="", driver_provider="", driver_version="N/A", driver_date="N/A",
                       hardware_ids=None):
    return {
        "instance_id": instance_id,
        "description": description,
        "class_name": class_name,
        "manufacturer": manufacturer,
        "status": status,
        "driver_name": driver_name,
        "driver_provider": driver_provider,
        "driver_version": driver_version,
        "driver_date": driver_date,
        "hardware_ids": list(hardware_ids or []),
        "category": "Other",
        "vendor": "Unknown",
        "vendor_url": "",
        "primary_hwid": "",
        "fallback_hwid": "",
        "is_primary": False,
        "is_storage": False,
        "catalog_status": "Ready to Check",
        "latest_version": "-",
        "latest_date": "-",
        "download_url": "",
        "catalog_url": "",
        "oem_note": "",
        "is_inbox": False,
    }


def _split_driver_version(value):
    """'03/31/2024 10.0.26100.1' -> ('03/31/2024', '10.0.26100.1')."""
    match = re.match(r"^\s*(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})\s+(\S+)\s*$", value or "")
    if match:
        return match.group(1), match.group(2)
    return "N/A", (value or "N/A").strip()


def _decode_console(raw):
    """Windows tools write the OEM codepage, not UTF-8."""
    if isinstance(raw, str):
        return raw
    candidates = ["utf-8"]
    try:
        import ctypes
        candidates.append("cp%d" % ctypes.windll.kernel32.GetOEMCP())
    except Exception:
        pass
    candidates.append("cp1252")
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("latin-1", "replace")


def _arch_matches(products, arch):
    text = (products or "").lower()
    if arch == "ARM64":
        return "arm64" in text or "aarch64" in text
    if arch == "x86":
        return "x64" not in text and "arm64" not in text
    return "arm64" not in text


def _pnp_devices_xml():
    """Locale-independent device list via pnputil's XML mode.

    pnputil's *text* output is translated on non-English Windows, which made the
    old label-based parser return zero devices. XML element names are fixed
    schema names and the file is UTF-8, so this works on any locale.
    Returns None when the build does not support it.
    """
    import tempfile
    import xml.etree.ElementTree as ET

    path = os.path.join(tempfile.gettempdir(), "driverfinder-pnp-%d.xml" % os.getpid())
    try:
        proc = subprocess.run(
            ["pnputil", "/enum-devices", "/connected", "/drivers", "/deviceids",
             "/format", "xml", "/output-file", path],
            capture_output=True,
            timeout=90,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
        if proc.returncode != 0 or not os.path.exists(path):
            return None
        tree = ET.parse(path)
    except Exception:
        return None
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    devices = []
    try:
        root = tree.getroot()
        for node in root.findall("Device"):
            def text_of(tag):
                child = node.find(tag)
                return (child.text or "").strip() if child is not None and child.text else ""

            hardware_ids = [
                (item.text or "").strip()
                for item in node.findall("HardwareIds/HardwareId")
                if item.text
            ]

            bound_driver = text_of("DriverName")
            provider = ""
            version = "N/A"
            date = "N/A"
            matching = node.findall("MatchingDrivers/DriverName")
            chosen = None
            for entry in matching:
                if bound_driver and (entry.get("DriverName") or "").lower() == bound_driver.lower():
                    chosen = entry
                    break
            if chosen is None and matching:
                chosen = matching[0]
            if chosen is not None:
                child = chosen.find("ProviderName")
                if child is not None and child.text:
                    provider = child.text.strip()
                child = chosen.find("DriverVersion")
                if child is not None and child.text:
                    date, version = _split_driver_version(child.text)
            if not provider:
                provider = text_of("ManufacturerName")

            devices.append(_new_device_record(
                instance_id=node.get("InstanceId", ""),
                description=text_of("DeviceDescription"),
                class_name=text_of("ClassName"),
                manufacturer=text_of("ManufacturerName"),
                status=text_of("Status") or "Healthy",
                driver_name=bound_driver,
                driver_provider=provider,
                driver_version=version,
                driver_date=date,
                hardware_ids=hardware_ids,
            ))
    except Exception:
        return None

    return devices


def _pnp_devices_text():
    """Fallback for builds without /format xml. English Windows only."""
    try:
        proc = subprocess.run(
            ["pnputil", "/enum-devices", "/connected", "/drivers", "/ids"],
            capture_output=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
        output = _decode_console(proc.stdout)
    except Exception as exc:
        print(f"Error running pnputil: {exc}")
        return []

    entries = re.split(r'\n(?=Instance ID:\s+)', output)
    devices = []
    for entry in entries:
        if not entry.strip().startswith("Instance ID:"):
            continue

        dev = _new_device_record()
        current_section = None
        for line in entry.splitlines():
            if line.startswith("Instance ID:"):
                dev["instance_id"] = line.split(":", 1)[1].strip()
            elif line.startswith("Device Description:"):
                dev["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("Class Name:"):
                dev["class_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Manufacturer Name:"):
                dev["manufacturer"] = line.split(":", 1)[1].strip()
            elif line.startswith("Status:"):
                dev["status"] = line.split(":", 1)[1].strip()
            elif line.startswith("Driver Name:") and not dev["driver_name"]:
                dev["driver_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Hardware IDs:"):
                current_section = "hardware_ids"
                first_id = line.split(":", 1)[1].strip()
                if first_id:
                    dev["hardware_ids"].append(first_id)
            elif line.startswith("Matching Drivers:"):
                current_section = "matching_drivers"
            elif line.startswith("    Provider Name:") and current_section == "matching_drivers" and not dev["driver_provider"]:
                dev["driver_provider"] = line.split(":", 1)[1].strip()
            elif line.startswith("    Driver Version:") and current_section == "matching_drivers" and dev["driver_version"] == "N/A":
                date, version = _split_driver_version(line.split(":", 1)[1].strip())
                dev["driver_date"] = date
                dev["driver_version"] = version
            elif current_section == "hardware_ids" and line.startswith("    ") and not line.startswith("Matching Drivers"):
                hardware_id = line.strip()
                if hardware_id and ":" not in hardware_id:
                    dev["hardware_ids"].append(hardware_id)
            elif not line.startswith("    ") and not line.startswith("Hardware IDs:"):
                current_section = None

        devices.append(dev)
    return devices


def scan_devices():
    global LAST_SCAN_ERROR
    LAST_SCAN_ERROR = ""

    raw_devices = _pnp_devices_xml()
    used_xml = raw_devices is not None
    if raw_devices is None:
        raw_devices = _pnp_devices_text()

    if not raw_devices:
        build = windows_build_number()
        if 0 < build < 18362:
            LAST_SCAN_ERROR = (
                "This Windows build (%d) predates Windows 10 1903, which introduced the "
                "device enumeration commands Driver Finder uses." % build
            )
        else:
            LAST_SCAN_ERROR = (
                "Windows returned no devices. The pnputil command may be blocked by "
                "security software or a policy."
            )
        return []

    devices = []
    seen_processor = False

    for dev in raw_devices:
        if not dev["description"]:
            continue

        cname = dev["class_name"].lower()
        desc_lower = dev["description"].lower()
        drv_lower = dev["driver_name"].lower()

        # Check if driver is standard Windows inbox driver
        if drv_lower in MICROSOFT_INBOX_INFS or dev["driver_provider"].lower() == "microsoft":
            if cname not in ["display", "net", "media", "bluetooth"]:
                dev["is_inbox"] = True
                # Resolve the status now, so the row never looks like it is
                # waiting to be checked.
                dev["catalog_status"] = "Windows-Managed"

        if cname in ["display"]:
            dev["category"] = "Display & Graphics"
            dev["is_primary"] = True
        elif cname in ["net"]:
            if any(term in desc_lower for term in ["wan miniport", "kernel debug", "direct virtual", "personal area network", "tap-"]):
                dev["category"] = "Virtual Network"
                dev["is_primary"] = False
            else:
                dev["category"] = "Network & Wi-Fi"
                dev["is_primary"] = True
        elif cname in ["media"]:
            dev["category"] = "Audio & Sound"
            if any(term in desc_lower for term in ["audio", "sound", "realtek", "intel(r) display"]) and not any(term in desc_lower for term in ["proxy", "hands-free", "endpoint"]):
                dev["is_primary"] = True
        elif cname in ["audioendpoint"]:
            dev["category"] = "Audio Endpoints"
            dev["is_primary"] = False
        elif cname in ["bluetooth"]:
            dev["category"] = "Bluetooth"
            if any(term in desc_lower for term in ["wireless bluetooth", "adapter", "radio", "controller"]) and not any(term in desc_lower for term in ["enumerator", "server", "pan"]):
                dev["is_primary"] = True
        elif cname in ["diskdrive"]:
            dev["category"] = "Storage & Drives"
            dev["is_storage"] = True
            dev["is_primary"] = True
        elif cname in ["scsiadapter", "hdc"]:
            dev["category"] = "Storage Controllers"
            # Replacing a boot-critical storage driver the wrong way leaves the
            # machine unbootable, so these need an explicit opt-in.
            dev["is_storage"] = True
            if "storage spaces" not in desc_lower:
                dev["is_primary"] = True
        elif cname in ["processor"]:
            dev["category"] = "Processors"
            if not seen_processor:
                dev["is_primary"] = True
                seen_processor = True
        elif cname in ["camera", "image"]:
            dev["category"] = "Camera & Imaging"
            # Built-in UVC webcams use Windows inbox usbvideo.inf
            dev["is_primary"] = False
            dev["is_inbox"] = True
        elif cname in ["usb", "usbdevice"]:
            dev["category"] = "USB Controllers"
            if "host controller" in desc_lower or "root hub" in desc_lower:
                dev["is_primary"] = True
        elif cname in ["system"]:
            dev["category"] = "System & Chipset"
            if any(term in desc_lower for term in ["management engine", "chipset", "serial io", "lpc"]) and not dev["is_inbox"]:
                dev["is_primary"] = True
        elif cname in ["mouse", "keyboard", "hidclass"]:
            dev["category"] = "Input Devices"
        else:
            dev["category"] = "System Devices"

        # Hardware Vendor
        for hid in dev["hardware_ids"]:
            m = re.search(r'VEN_([0-9A-Fa-f]{4})', hid)
            if m:
                ven_id = m.group(1).upper()
                if ven_id in VENDOR_PCI_MAP:
                    dev["vendor"] = VENDOR_PCI_MAP[ven_id]
                    break
            m_usb = re.search(r'VID_([0-9A-Fa-f]{4})', hid)
            if m_usb:
                vid_id = m_usb.group(1).upper()
                if vid_id in VENDOR_PCI_MAP:
                    dev["vendor"] = VENDOR_PCI_MAP[vid_id]
                    break

        if dev["vendor"] == "Unknown":
            combined = f"{dev['manufacturer']} {dev['driver_provider']} {dev['description']}".lower()
            if "intel" in combined:
                dev["vendor"] = "Intel"
            elif "nvidia" in combined:
                dev["vendor"] = "NVIDIA"
            elif "amd" in combined or "radeon" in combined:
                dev["vendor"] = "AMD"
            elif "realtek" in combined:
                dev["vendor"] = "Realtek"
            elif "qualcomm" in combined:
                dev["vendor"] = "Qualcomm"
            elif "broadcom" in combined:
                dev["vendor"] = "Broadcom"
            elif "samsung" in combined:
                dev["vendor"] = "Samsung"
            elif "dell" in combined:
                dev["vendor"] = "Dell"
            elif "microsoft" in combined:
                dev["vendor"] = "Microsoft"

        if dev["vendor"] in VENDOR_PORTALS:
            dev["vendor_url"] = VENDOR_PORTALS[dev["vendor"]]

        # Select Best Hardware ID preserving OEM Subsystem ID
        for hid in dev["hardware_ids"]:
            # 1. 4-part ID with SUBSYS
            m_sub = re.match(r'(PCI\\VEN_[0-9A-Fa-f]{4}&DEV_[0-9A-Fa-f]{4}&SUBSYS_[0-9A-Fa-f]{8})', hid, re.IGNORECASE)
            if not m_sub:
                m_sub = re.match(r'(HDAUDIO\\FUNC_[0-9A-Fa-f]{2}&VEN_[0-9A-Fa-f]{4}&DEV_[0-9A-Fa-f]{4}&SUBSYS_[0-9A-Fa-f]{8})', hid, re.IGNORECASE)
            if m_sub:
                dev["primary_hwid"] = m_sub.group(1)
                break

            # 2. USB VID/PID
            m_usb = re.match(r'(USB\\VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4})', hid, re.IGNORECASE)
            if m_usb:
                dev["primary_hwid"] = m_usb.group(1)
                break

        # Fallback 2-part ID
        for hid in dev["hardware_ids"]:
            m_2part = re.match(r'(PCI\\VEN_[0-9A-Fa-f]{4}&DEV_[0-9A-Fa-f]{4})', hid, re.IGNORECASE)
            if not m_2part:
                m_2part = re.match(r'(HDAUDIO\\FUNC_[0-9A-Fa-f]{2}&VEN_[0-9A-Fa-f]{4}&DEV_[0-9A-Fa-f]{4})', hid, re.IGNORECASE)
            if m_2part:
                dev["fallback_hwid"] = m_2part.group(1)
                if not dev["primary_hwid"]:
                    dev["primary_hwid"] = m_2part.group(1)
                break

        if not dev["primary_hwid"] and dev["hardware_ids"]:
            dev["primary_hwid"] = dev["hardware_ids"][0]

        search_query = dev["primary_hwid"] or dev["description"]
        dev["catalog_url"] = f"https://www.catalog.update.microsoft.com/Search.aspx?q={urllib.parse.quote(search_query)}"

        devices.append(dev)

    return devices


def parse_version_tuple(v_str):
    if not v_str or v_str.lower() in ['n/a', '-']:
        return ()
    nums = re.findall(r'\d+', v_str)
    return tuple(int(n) for n in nums)


def parse_date(d_str):
    if not d_str or d_str.lower() in ['n/a', '-']:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%y',
                '%d.%m.%Y', '%d.%m.%y', '%Y/%m/%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(d_str.strip(), fmt)
        except ValueError:
            pass
    return None


def compare_driver_versions(installed_ver, installed_date, catalog_ver, catalog_date):
    inst_v = parse_version_tuple(installed_ver)
    cat_v = parse_version_tuple(catalog_ver)
    inst_d = parse_date(installed_date)
    cat_d = parse_date(catalog_date)

    if inst_v and cat_v:
        min_len = min(len(inst_v), len(cat_v))
        if cat_v[:min_len] > inst_v[:min_len]:
            return "Update Available"
        elif cat_v[:min_len] < inst_v[:min_len]:
            if cat_d and inst_d and cat_d > inst_d:
                return "Update Available"
            return "Up to Date"
        else:
            if len(cat_v) > len(inst_v) and cat_v[min_len:] > (0,) * (len(cat_v) - min_len):
                return "Update Available"
            return "Up to Date"

    if cat_d and inst_d:
        if cat_d > inst_d:
            return "Update Available"
        return "Up to Date"

    return "Up to Date"


def fetch_direct_download_link(update_id):
    if not update_id:
        return ""
    try:
        url = "https://www.catalog.update.microsoft.com/DownloadDialog.aspx"
        post_data = f'updateIDs=[{{"size":0,"languages":"","uidInfo":"{update_id}","updateID":"{update_id}"}}]'.encode('utf-8')
        req = urllib.request.Request(
            url,
            data=post_data,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            links = re.findall(r'downloadInformation\[\d+\]\.files\[\d+\]\.url\s*=\s*[\'"]([^\'"]+)[\'"]', html)
            if not links:
                links = re.findall(r'https?://[^\'"]+windowsupdate\.com[^\'"]+', html)
            if links:
                return links[0]
    except Exception:
        pass
    return ""


def check_catalog_driver(query):
    """Backwards-compatible wrapper: returns [] instead of raising."""
    try:
        return catalog.query_catalog(query)
    except catalog.CatalogError as exc:
        print(f"Catalog query failed for '{query}': {exc}")
        return []


def check_catalog_driver_strict(query):
    """Raises catalog.CatalogError so 'offline' is not reported as 'up to date'."""
    return catalog.query_catalog(query)


def check_device_update(device):
    """
    Subsystem-aware update checking:
    1. If device is managed by Windows inbox driver (e.g. machine.inf), mark Up to Date.
    2. Queries exact 4-part subsystem ID to guarantee OEM compatibility (Dell, HP, Lenovo).
    3. Handles OEM graphics lock (Intel HD Graphics 620 on Dell).
    """
    # Check if Windows inbox managed
    if device.get("is_inbox") or device.get("driver_name", "").lower() in MICROSOFT_INBOX_INFS:
        device["catalog_status"] = "Windows-Managed"
        device["latest_version"] = device.get("driver_version", "N/A")
        device["latest_date"] = device.get("driver_date", "N/A")
        device["oem_note"] = (
            "Built into Windows. This driver ships and updates with the operating system, "
            "so Driver Finder cannot change it. Windows Update installs newer versions."
        )
        return device

    queries = []
    if device.get("primary_hwid"):
        queries.append(device["primary_hwid"])
    if device.get("fallback_hwid"):
        queries.append(device["fallback_hwid"])
    if device.get("description"):
        clean_desc = re.sub(r'\(R\)|\(TM\)|\[.*?\]', '', device["description"]).strip()
        if clean_desc:
            queries.append(clean_desc)

    results = []
    failures = 0
    for query in queries:
        try:
            results = check_catalog_driver_strict(query)
        except catalog.CatalogError:
            failures += 1
            continue
        if results:
            break

    if not results:
        if queries and failures == len(queries):
            device["catalog_status"] = "Check Failed"
            device["oem_note"] = "Could not reach the Microsoft Update Catalog. Check the connection and try again."
        else:
            device["catalog_status"] = "Up to Date / OEM"
        device["latest_version"] = device.get("driver_version", "N/A")
        device["latest_date"] = device.get("driver_date", "N/A")
        device["download_url"] = device.get("vendor_url") or device.get("catalog_url")
        return device

    arch = get_architecture()
    best_candidate = None
    for r in results:
        prod = r["products"].lower()
        if not _arch_matches(prod, arch):
            continue  # e.g. x64 package on an ARM64 machine would fail to install
        if any(term in prod for term in ["windows 10", "windows 11", "client", "x64", "arm64"]):
            best_candidate = r
            break

    if not best_candidate and results:
        compatible = [r for r in results if _arch_matches(r["products"], arch)]
        if compatible:
            best_candidate = compatible[0]

    if not best_candidate:
        device["catalog_status"] = "Up to Date / OEM"
        device["latest_version"] = device.get("driver_version", "N/A")
        device["latest_date"] = device.get("driver_date", "N/A")
        device["download_url"] = device.get("catalog_url") or device.get("vendor_url")
        device["oem_note"] = (
            "The catalog lists this device, but no package matches this PC's "
            "architecture (%s)." % arch
        )
        return device

    if best_candidate:
        device["latest_version"] = best_candidate["version"]
        device["latest_date"] = best_candidate["date"]
        
        cmp_result = compare_driver_versions(
            device["driver_version"],
            device["driver_date"],
            best_candidate["version"],
            best_candidate["date"]
        )

        for rule in OEM_HWID_RULES:
            if rule["match"] not in device.get("primary_hwid", ""):
                continue
            if rule.get("oem") and rule["oem"] not in system_manufacturer():
                continue
            if rule.get("only_if_version") and device.get("driver_version") != rule["only_if_version"]:
                continue
            if rule.get("download_url"):
                device["download_url"] = rule["download_url"]
            if rule.get("latest_version"):
                device["latest_version"] = rule["latest_version"]
            if rule.get("latest_date"):
                device["latest_date"] = rule["latest_date"]
            if rule.get("note"):
                device["oem_note"] = rule["note"]
            cmp_result = compare_driver_versions(
                device["driver_version"],
                device["driver_date"],
                device["latest_version"],
                device["latest_date"]
            )
            if rule.get("force_up_to_date"):
                cmp_result = "Up to Date"
            break

        device["catalog_status"] = cmp_result

        if not device.get("download_url"):
            if cmp_result == "Update Available":
                dl_link = fetch_direct_download_link(best_candidate["update_id"])
                if dl_link:
                    device["download_url"] = dl_link
                else:
                    device["download_url"] = device["catalog_url"]
            else:
                device["download_url"] = device["catalog_url"]

    return device