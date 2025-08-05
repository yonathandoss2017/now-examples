#!/usr/bin/env python3
"""
Git Dumper

Una herramienta para descargar repositorios de Git expuestos en servidores web.
Esta versión mejorada incluye detección de "Smart HTTP", barras de progreso,
registro avanzado y listas de archivos ampliadas.

Dependencias:
pip install requests beautifulsoup4 dulwich pysocks requests_pkcs12 tqdm urllib3
"""
from contextlib import closing
import argparse
import logging
import multiprocessing
import os
import os.path
import re
import shutil
import socket
import subprocess
import sys
import traceback
import urllib.parse
from typing import List, Tuple, Dict, Any, Optional, Set

import urllib3
import bs4
import dulwich.index
import dulwich.objects
import dulwich.pack
import requests
import socks
from requests_pkcs12 import Pkcs12Adapter
from tqdm import tqdm


def is_html(response: requests.Response) -> bool:
    """ Devuelve True si la respuesta es una página web HTML """
    return (
        "Content-Type" in response.headers
        and "text/html" in response.headers["Content-Type"]
    )


def is_safe_path(path: str) -> bool:
    """ Previene ataques de directory traversal """
    if os.path.isabs(path) or ".." in path.split(os.path.sep):
        return False
    
    # Crea una ruta base segura dentro del directorio actual
    safe_base = os.path.realpath(os.getcwd())
    
    # Comprueba que la ruta final no salga del directorio de trabajo
    final_path = os.path.realpath(os.path.join(safe_base, path))
    return os.path.commonpath([safe_base, final_path]) == safe_base


def get_indexed_files(response: requests.Response) -> List[str]:
    """ Devuelve todos los archivos en la página de índice del directorio """
    html = bs4.BeautifulSoup(response.text, "html.parser")
    files = []

    for link in html.find_all("a"):
        url = urllib.parse.urlparse(link.get("href"))

        # Ignorar enlaces con esquemas, ubicaciones de red o rutas absolutas
        if (
            url.path
            and not url.path.endswith("/") # Ignorar directorios padres
            and not url.scheme
            and not url.netloc
        ):
            # Decodificar caracteres especiales en la URL (ej. %20 -> espacio)
            decoded_path = urllib.parse.unquote(url.path)
            if is_safe_path(decoded_path):
                files.append(decoded_path)

    return files


def verify_response(response: requests.Response) -> Tuple[bool, str]:
    """ Verifica si la respuesta del servidor es válida para ser descargada """
    if response.status_code != 200:
        return (
            False,
            f"URL respondió con el código de estado {response.status_code}",
        )
    if "Content-Length" in response.headers and response.headers["Content-Length"] == "0":
        return False, "URL respondió con un cuerpo de longitud cero"
    if is_html(response):
        return False, "URL respondió con HTML en lugar de un archivo"
    
    return True, ""


def create_intermediate_dirs(path: str) -> None:
    """ Crea directorios intermedios si es necesario """
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        try:
            os.makedirs(dirname)
        except FileExistsError:
            pass  # Condición de carrera


def get_referenced_sha1(obj_file: dulwich.objects.ShaFile) -> List[str]:
    """ Devuelve todos los SHA1 referenciados en el archivo de objeto dado """
    objs = []
    if isinstance(obj_file, dulwich.objects.Commit):
        objs.append(obj_file.tree.decode('ascii'))
        for parent in obj_file.parents:
            objs.append(parent.decode('ascii'))
    elif isinstance(obj_file, dulwich.objects.Tree):
        for item in obj_file.iteritems():
            objs.append(item.sha.decode('ascii'))
    elif isinstance(obj_file, dulwich.objects.Blob):
        pass  # Los blobs no referencian otros objetos
    elif isinstance(obj_file, dulwich.objects.Tag):
        if obj_file.object:
            objs.append(obj_file.object[1].decode('ascii'))
    else:
        logging.error(f"Tipo de objeto inesperado: {obj_file!r}")
        sys.exit(1)

    return objs


class Worker(multiprocessing.Process):
    """ Worker para procesar tareas en paralelo """

    def __init__(self, pending_tasks: multiprocessing.Queue, tasks_done: multiprocessing.Queue, args: tuple):
        super().__init__()
        self.daemon = True
        self.pending_tasks = pending_tasks
        self.tasks_done = tasks_done
        self.args = args

    def run(self) -> None:
        self.init(*self.args)
        while True:
            task = self.pending_tasks.get(block=True)
            if task is None:  # Señal de fin
                return
            try:
                result = self.do_task(task, *self.args)
            except Exception:
                logging.error(f"Tarea {task} generó una excepción:")
                traceback.print_exc()
                result = []
            
            assert isinstance(result, list), "do_task() debe devolver una lista de tareas"
            self.tasks_done.put((task, result))

    def init(self, *args: Any) -> None:
        raise NotImplementedError

    def do_task(self, task: Any, *args: Any) -> List[Any]:
        raise NotImplementedError


def process_tasks(initial_tasks: list, worker: type, jobs: int, args: tuple = (), tasks_done_set: Optional[set] = None) -> None:
    """ Procesa tareas en paralelo con una barra de progreso """
    if not initial_tasks:
        return

    tasks_seen = tasks_done_set if tasks_done_set is not None else set()
    pending_tasks = multiprocessing.Queue()
    tasks_done_queue = multiprocessing.Queue()
    num_pending_tasks = 0

    for task in initial_tasks:
        if task not in tasks_seen:
            pending_tasks.put(task)
            num_pending_tasks += 1
            tasks_seen.add(task)

    if num_pending_tasks == 0:
        logging.info("No hay tareas nuevas para procesar.")
        return

    processes = [worker(pending_tasks, tasks_done_queue, args) for _ in range(jobs)]
    for p in processes:
        p.start()

    with tqdm(total=num_pending_tasks, desc="Descargando", unit="file") as pbar:
        tasks_processed = 0
        while tasks_processed < num_pending_tasks:
            try:
                original_task, new_tasks = tasks_done_queue.get(block=True, timeout=0.1)
                pbar.update(1)
                tasks_processed += 1

                for task in new_tasks:
                    if task not in tasks_seen:
                        tasks_seen.add(task)
                        pending_tasks.put(task)
                        num_pending_tasks += 1
                        pbar.total = num_pending_tasks
            except multiprocessing.queues.Empty:
                # Comprobar si algún proceso ha muerto
                if not any(p.is_alive() for p in processes):
                    logging.error("Todos los workers han terminado inesperadamente.")
                    break

    for _ in range(jobs):
        pending_tasks.put(None)

    for p in processes:
        p.join()


class DownloadWorker(Worker):
    """ Descarga una lista de archivos """
    def init(self, url, directory, retry, timeout, http_headers, client_cert_p12=None, client_cert_p12_password=None):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(http_headers)
        adapter_args = {}
        if client_cert_p12:
            self.session.mount(url, Pkcs12Adapter(pkcs12_filename=client_cert_p12, pkcs12_password=client_cert_p12_password))
        else:
            adapter = requests.adapters.HTTPAdapter(max_retries=retry)
            self.session.mount(url, adapter)

    def do_task(self, filepath: str, url: str, directory: str, retry: int, timeout: int, http_headers: Dict, client_cert_p12: Optional[str] = None, client_cert_p12_password: Optional[str] = None) -> List:
        full_path = os.path.join(directory, filepath)
        if os.path.exists(full_path):
            return []

        try:
            with closing(self.session.get(f"{url}/{filepath}", allow_redirects=False, stream=True, timeout=timeout)) as response:
                valid, error_message = verify_response(response)
                if not valid:
                    return []
                
                abspath = os.path.abspath(full_path)
                create_intermediate_dirs(abspath)
                with open(abspath, "wb") as f:
                    for chunk in response.iter_content(4096):
                        f.write(chunk)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Error al descargar {url}/{filepath}: {e}")
            return []
        
        return []


class RecursiveDownloadWorker(DownloadWorker):
    """ Descarga un directorio recursivamente """
    def do_task(self, filepath: str, url: str, directory: str, retry: int, timeout: int, http_headers: Dict) -> List[str]:
        full_path = os.path.join(directory, filepath)
        if os.path.exists(full_path) and os.path.isfile(full_path):
             return []

        try:
            with closing(self.session.get(f"{url}/{filepath}", allow_redirects=False, stream=True, timeout=timeout)) as response:
                if response.status_code in (301, 302) and response.headers.get("Location", "").endswith(filepath + "/"):
                    return [filepath + "/"]

                if filepath.endswith("/"):  # Índice de directorio
                    if is_html(response):
                        return [filepath + filename for filename in get_indexed_files(response)]
                    else:
                        return []
                else:  # Archivo
                    valid, error_message = verify_response(response)
                    if not valid:
                        return []

                    abspath = os.path.abspath(full_path)
                    create_intermediate_dirs(abspath)
                    with open(abspath, "wb") as f:
                        for chunk in response.iter_content(4096):
                            f.write(chunk)
                    return []
        except requests.exceptions.RequestException as e:
            logging.warning(f"Error al descargar recursivamente {url}/{filepath}: {e}")
            return []


class FindRefsWorker(DownloadWorker):
    """ Encuentra y descarga archivos de referencias (refs) """
    def do_task(self, filepath: str, url: str, directory: str, retry: int, timeout: int, http_headers: Dict, client_cert_p12: Optional[str] = None, client_cert_p12_password: Optional[str] = None) -> List[str]:
        full_path = os.path.join(directory, filepath)
        if os.path.exists(full_path):
            return []

        try:
            response = self.session.get(f"{url}/{filepath}", allow_redirects=False, timeout=timeout)
            valid, error_message = verify_response(response)
            if not valid:
                return []
            
            abspath = os.path.abspath(full_path)
            create_intermediate_dirs(abspath)
            with open(abspath, "w", encoding='utf-8') as f:
                f.write(response.text)

            tasks = []
            for ref_match in re.finditer(r"(refs(?:/[a-zA-Z0-9\-\.\_\*]+)+)", response.text):
                ref = ref_match.group(0)
                if not ref.endswith("*") and is_safe_path(ref):
                    tasks.append(f".git/{ref}")
                    tasks.append(f".git/logs/{ref}")
            return tasks

        except requests.exceptions.RequestException as e:
            logging.warning(f"Error buscando refs en {url}/{filepath}: {e}")
            return []


class FindObjectsWorker(DownloadWorker):
    """ Encuentra y descarga objetos de git """
    def do_task(self, obj: str, url: str, directory: str, retry: int, timeout: int, http_headers: Dict, client_cert_p12: Optional[str] = None, client_cert_p12_password: Optional[str] = None) -> List[str]:
        filepath = f".git/objects/{obj[:2]}/{obj[2:]}"
        abspath = os.path.abspath(os.path.join(directory, filepath))

        if not os.path.exists(abspath):
            try:
                response = self.session.get(f"{url}/{filepath}", allow_redirects=False, timeout=timeout)
                valid, _ = verify_response(response)
                if not valid:
                    return []

                create_intermediate_dirs(abspath)
                with open(abspath, "wb") as f:
                    f.write(response.content)
            except requests.exceptions.RequestException:
                return []
        
        try:
            with open(abspath, 'rb') as f:
                obj_file = dulwich.objects.ShaFile(f.read())
                return get_referenced_sha1(obj_file.obj)
        except Exception:
            return []


def sanitize_file(filepath: str) -> None:
    """ Comenta líneas posiblemente inseguras en archivos de configuración """
    if not os.path.isfile(filepath):
        logging.warning(f"No se pudo sanitizar '{filepath}', no es un archivo.")
        return

    # Regex para comandos que pueden ejecutar código o contactar redes
    UNSAFE_RE = re.compile(r"^\s*(fsmonitor|sshcommand|askpass|editor|pager|proxy)", re.IGNORECASE)
    
    try:
        with open(filepath, 'r+') as f:
            lines = f.readlines()
            f.seek(0)
            modified = False
            for line in lines:
                if UNSAFE_RE.match(line):
                    f.write(f'# {line}')
                    modified = True
                else:
                    f.write(line)
            f.truncate()
            if modified:
                logging.warning(f"Se han comentado líneas potencialmente inseguras en '{filepath}'")
    except Exception as e:
        logging.error(f"No se pudo leer o modificar el archivo '{filepath}': {e}")


def fetch_git(url: str, directory: str, jobs: int, retry: int, timeout: int, http_headers: Dict, client_cert_p12: Optional[str], client_cert_p12_password: Optional[str]) -> int:
    """ Descarga un repositorio git al directorio de salida """
    assert os.path.isdir(directory), f"'{directory}' no es un directorio"
    
    session = requests.Session()
    session.verify = False
    session.headers.update(http_headers)
    if client_cert_p12:
        session.mount(url, Pkcs12Adapter(pkcs12_filename=client_cert_p12, pkcs12_password=client_cert_p12_password))
    else:
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount(url, adapter)

    if os.listdir(directory):
        logging.warning(f"El directorio de destino '{directory}' no está vacío.")

    url = url.rstrip("/")
    if url.endswith("/.git"):
        url = url[:-5]

    logging.info(f"Probando la existencia de .git en: {url}/.git/")
    
    # Entorno para subprocesos (git) que respeta la configuración de proxy
    environment = os.environ.copy()
    if socks.getdefaultproxy():
        proxy_type, proxy_addr, proxy_port, _, _, _ = socks.getdefaultproxy()
        proxy_map = {socks.PROXY_TYPE_HTTP: 'http', socks.PROXY_TYPE_SOCKS4: 'socks4h', socks.PROXY_TYPE_SOCKS5: 'socks5h'}
        if proxy_type in proxy_map:
            environment["ALL_PROXY"] = f"{proxy_map[proxy_type]}://{proxy_addr}:{proxy_port}"

    # --- 1. Probar el protocolo "Smart HTTP" ---
    logging.info("Probando si es un servidor 'smart' de git...")
    smart_http_url = f"{url}/.git/info/refs?service=git-upload-pack"
    try:
        response = session.get(smart_http_url, timeout=timeout)
        is_smart = (
            response.status_code == 200
            and "application/x-git-upload-pack-advertisement" in response.headers.get("Content-Type", "")
            and "# service=git-upload-pack" in response.text
        )
        if is_smart and shutil.which("git"):
            logging.info("Servidor 'smart' detectado. Usando 'git clone' para una descarga más rápida.")
            try:
                subprocess.check_call(["git", "clone", "--mirror", f"{url}/.git", directory], env=environment)
                logging.info("Clonación 'mirror' completada. Configurando para checkout.")
                
                os.chdir(directory)
                sanitize_file("config")
                
                subprocess.check_call(["git", "config", "--bool", "core.bare", "false"])
                subprocess.check_call(["git", "reset", "--hard"])
                
                logging.info(f"[+] Repositorio descargado y restaurado en '{directory}'.")
                return 0
            except subprocess.CalledProcessError as e:
                logging.warning(f"'git clone' falló: {e}. Se intentará el método manual.")
            except FileNotFoundError:
                 logging.warning("'git' no encontrado. Se intentará el método manual.")
        else:
            logging.info("No es un servidor 'smart' o 'git' no está en el PATH. Procediendo con el método manual.")
    except requests.exceptions.RequestException as e:
        logging.warning(f"La comprobación de servidor 'smart' falló: {e}. Procediendo con el método manual.")

    # --- 2. Probar HEAD para confirmar la existencia del repositorio ---
    try:
        head_response = session.get(f"{url}/.git/HEAD", timeout=timeout, allow_redirects=False)
        valid, error_message = verify_response(head_response)
        if not valid or not re.match(r"^(ref:.*|[0-9a-f]{40})", head_response.text.strip()):
            logging.error(f"No se pudo obtener un archivo HEAD válido de git: {error_message}")
            return 1
    except requests.exceptions.RequestException as e:
        logging.error(f"No se pudo conectar a {url}/.git/HEAD: {e}")
        return 1

    # --- 3. Probar si el listado de directorios está habilitado ---
    try:
        dir_response = session.get(f"{url}/.git/", allow_redirects=False, timeout=timeout)
        if dir_response.status_code == 200 and is_html(dir_response) and "HEAD" in get_indexed_files(dir_response):
            logging.info("Listado de directorios detectado. Descargando recursivamente .git.")
            process_tasks(
                [".git/"], RecursiveDownloadWorker, jobs, 
                args=(url, directory, retry, timeout, http_headers)
            )
            os.chdir(directory)
            sanitize_file(".git/config")
            logging.info("Ejecutando 'git checkout .'")
            subprocess.check_call(["git", "checkout", "."], env=environment)
            return 0
    except requests.exceptions.RequestException:
        pass # Continuar con el método manual

    # --- 4. Método manual: descargar archivos uno por uno ---
    logging.info("Listado de directorios no disponible. Iniciando descarga manual de archivos.")
    
    # Listas de archivos a descargar
    common_files = [
        ".gitignore", ".git/COMMIT_EDITMSG", ".git/description",
        ".git/index", ".git/info/exclude", ".git/objects/info/packs",
    ]
    process_tasks(
        common_files, DownloadWorker, jobs, 
        args=(url, directory, retry, timeout, http_headers, client_cert_p12, client_cert_p12_password),
    )
    
    # Búsqueda de referencias
    logging.info("Buscando y descargando referencias (refs)...")
    base_refs = [".git/FETCH_HEAD", ".git/HEAD", ".git/ORIG_HEAD", ".git/config", ".git/info/refs", ".git/packed-refs", ".git/refs/stash", ".git/logs/HEAD", ".git/logs/refs/stash"]
    
    common_branches = ["main", "master", "dev", "develop", "development", "staging", "test", "testing", "production", "release", "hotfix"]
    ref_paths = [".git/refs/heads", ".git/refs/remotes/origin", ".git/logs/refs/heads", ".git/logs/refs/remotes/origin"]
    for base_path in ref_paths:
        for branch in common_branches:
            base_refs.append(f"{base_path}/{branch}")

    process_tasks(
        base_refs, FindRefsWorker, jobs,
        args=(url, directory, retry, timeout, http_headers, client_cert_p12, client_cert_p12_password),
    )
    
    # Búsqueda de packs
    logging.info("Buscando y descargando archivos pack...")
    pack_tasks = []
    info_packs_path = os.path.join(directory, ".git/objects/info/packs")
    if os.path.exists(info_packs_path):
        with open(info_packs_path, "r") as f:
            for sha1 in re.findall(r"pack-([a-f0-9]{40})\.pack", f.read()):
                pack_tasks.append(f".git/objects/pack/pack-{sha1}.idx")
                pack_tasks.append(f".git/objects/pack/pack-{sha1}.pack")
    process_tasks(
        pack_tasks, DownloadWorker, jobs,
        args=(url, directory, retry, timeout, http_headers, client_cert_p12, client_cert_p12_password),
    )

    # Búsqueda de objetos
    logging.info("Descubriendo objetos a partir de los archivos descargados...")
    objs: Set[str] = set()
    packed_objs: Set[str] = set()

    # Extraer SHAs de todos los archivos de referencias y logs
    git_dir = os.path.join(directory, ".git")
    for root, _, files in os.walk(git_dir):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                with open(path, "r", errors='ignore') as f:
                    for line in f:
                        for sha_match in re.finditer(r"\b([a-f0-9]{40})\b", line):
                            objs.add(sha_match.group(1))
            except (IOError, UnicodeDecodeError):
                continue
    
    # Extraer SHAs del índice
    index_path = os.path.join(directory, ".git/index")
    if os.path.exists(index_path):
        try:
            index = dulwich.index.Index(index_path)
            for entry in index.iterobjects():
                objs.add(entry[1].decode('ascii'))
        except Exception:
            logging.warning("No se pudo parsear el archivo de índice.")

    # Extraer SHAs de los packs y marcar objetos como ya descargados (packed)
    pack_dir = os.path.join(directory, ".git/objects/pack")
    if os.path.isdir(pack_dir):
        for filename in os.listdir(pack_dir):
            if filename.endswith(".pack"):
                idx_path = os.path.join(pack_dir, filename[:-5] + ".idx")
                if not os.path.exists(idx_path): continue
                try:
                    pack_idx = dulwich.pack.PackIndex(idx_path)
                    for sha_bytes in pack_idx:
                        packed_objs.add(sha_bytes.hex())
                except Exception:
                    logging.warning(f"No se pudo parsear el archivo de pack index {idx_path}.")

    logging.info(f"Descubiertos {len(objs)} objetos potenciales, {len(packed_objs)} ya están en packs.")
    process_tasks(
        list(objs), FindObjectsWorker, jobs,
        args=(url, directory, retry, timeout, http_headers, client_cert_p12, client_cert_p12_password),
        tasks_done_set=packed_objs,
    )
    
    # Checkout final
    logging.info("Ejecutando 'git checkout .' para restaurar los archivos...")
    os.chdir(directory)
    sanitize_file(".git/config")
    
    result = subprocess.run(["git", "checkout", "."], stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=environment)
    if result.returncode != 0:
        logging.warning("git checkout falló. El repositorio puede estar incompleto.")
        logging.warning(f"Stderr: {result.stderr.decode(errors='ignore')}")

    logging.info(f"Proceso completado. El repositorio se ha descargado en '{directory}'.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        usage="git_dumper.py [options] URL DIR",
        description="Descarga un repositorio de Git desde un sitio web. Dependencias: requests, beautifulsoup4, dulwich, pysocks, requests_pkcs12, tqdm.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("url", metavar="URL", help="URL base del repositorio (ej. http://example.com/web)")
    parser.add_argument("directory", metavar="DIR", help="Directorio de salida")
    
    # Opciones de Red
    net_group = parser.add_argument_group('Opciones de Red')
    net_group.add_argument("--proxy", help="Proxy a utilizar (ej. socks5://127.0.0.1:9050)")
    net_group.add_argument("-j", "--jobs", type=int, default=1, help="Número de peticiones simultáneas (default: 10)")
    net_group.add_argument("-r", "--retry", type=int, default=3, help="Número de reintentos por petición (default: 3)")
    net_group.add_argument("-t", "--timeout", type=int, default=10, help="Timeout en segundos para las peticiones (default: 10)")

    # Opciones de Petición
    req_group = parser.add_argument_group('Opciones de Petición')
    req_group.add_argument("-u", "--user-agent", default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36", help="User-Agent a utilizar")
    req_group.add_argument("-H", "--header", action="append", help="Cabecera HTTP adicional (formato: 'Nombre:Valor')")
    req_group.add_argument("--client-cert-p12", help="Certificado de cliente en formato PKCS#12")
    req_group.add_argument("--client-cert-p12-password", help="Contraseña para el certificado de cliente")

    args = parser.parse_args()

    # Configuración de logging
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

    # Validación de argumentos
    if args.jobs < 1: parser.error("el número de jobs debe ser >= 1")
    if args.retry < 1: parser.error("el número de reintentos debe ser >= 1")
    if args.timeout < 1: parser.error("el timeout debe ser >= 1")

    http_headers = {"User-Agent": args.user_agent}
    if args.header:
        for header in args.header:
            if ":" not in header:
                parser.error(f"la cabecera HTTP debe tener el formato 'Nombre:Valor', se recibió: '{header}'")
            name, value = header.split(":", 1)
            http_headers[name.strip()] = value.strip()

    if args.proxy:
        try:
            parsed_proxy = urllib.parse.urlparse(args.proxy)
            proxy_type_map = {'socks5': socks.PROXY_TYPE_SOCKS5, 'socks4': socks.PROXY_TYPE_SOCKS4, 'http': socks.PROXY_TYPE_HTTP}
            proxy_type = proxy_type_map.get(parsed_proxy.scheme)
            if not proxy_type:
                parser.error(f"esquema de proxy no válido: {parsed_proxy.scheme}")
            
            socks.setdefaultproxy(proxy_type, parsed_proxy.hostname, parsed_proxy.port)
            socket.socket = socks.socksocket
            logging.info(f"Usando proxy {parsed_proxy.scheme} en {parsed_proxy.hostname}:{parsed_proxy.port}")
        except Exception as e:
            parser.error(f"proxy inválido: {args.proxy}. Error: {e}")

    if not os.path.exists(args.directory):
        os.makedirs(args.directory)
    if not os.path.isdir(args.directory):
        parser.error(f"'{args.directory}' no es un directorio.")

    if args.client_cert_p12:
        if not os.path.isfile(args.client_cert_p12):
            parser.error(f"el archivo de certificado '{args.client_cert_p12}' no existe o no es un archivo.")
        if not args.client_cert_p12_password:
            parser.error("se requiere la contraseña del certificado de cliente.")

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        return fetch_git(
            args.url, args.directory, args.jobs, args.retry, args.timeout,
            http_headers, args.client_cert_p12, args.client_cert_p12_password
        )
    except KeyboardInterrupt:
        logging.info("\nProceso interrumpido por el usuario. Saliendo.")
        return 130 # Código de salida estándar para Ctrl+C
    except Exception as e:
        logging.error(f"Ha ocurrido un error inesperado: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
