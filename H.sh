#!/bin/bash

# Git Dumper
# A bash tool to download exposed Git repositories from web servers

# Dependencies: curl, git, find, sed, grep, awk, mkdir, wget (for recursive downloads)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default settings
JOBS=1
RETRY=3
TIMEOUT=10
USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
HEADERS=()

# Global variables
URL=""
DIRECTORY=""
PROXY=""
CLIENT_CERT_P12=""
CLIENT_CERT_P12_PASSWORD=""

# Helper functions
log_info() {
    echo -e "[$(date +%H:%M:%S)] [INFO] ${1}"
}

log_warning() {
    echo -e "[$(date +%H:%M:%S)] [${YELLOW}WARN${NC}] ${1}"
}

log_error() {
    echo -e "[$(date +%H:%M:%S)] [${RED}ERROR${NC}] ${1}" >&2
}

is_safe_path() {
    local path="$1"
    if [[ "$path" =~ ^/ || "$path" =~ \.\. ]]; then
        return 1
    fi
    return 0
}

verify_response() {
    local response_file="$1"
    local status_code=$(head -n 1 "$response_file" | awk '{print $2}')
    local content_type=$(grep -i "^content-type:" "$response_file" | head -n 1 | tr -d '\r')
    
    if [[ "$status_code" != "200" ]]; then
        echo "URL responded with status code $status_code"
        return 1
    fi
    
    if grep -i "^content-length: 0" "$response_file" >/dev/null; then
        echo "URL responded with zero-length body"
        return 1
    fi
    
    if [[ "$content_type" =~ text/html ]]; then
        echo "URL responded with HTML instead of a file"
        return 1
    fi
    
    return 0
}

download_file() {
    local url="$1"
    local output_file="$2"
    local headers=("${@:3}")
    
    mkdir -p "$(dirname "$output_file")"
    
    local curl_cmd=("curl" "-s" "-k" "-L" "--max-time" "$TIMEOUT" "--retry" "$RETRY" "-o" "$output_file")
    
    if [[ -n "$USER_AGENT" ]]; then
        curl_cmd+=("-A" "$USER_AGENT")
    fi
    
    for header in "${headers[@]}"; do
        curl_cmd+=("-H" "$header")
    done
    
    if [[ -n "$PROXY" ]]; then
        curl_cmd+=("--proxy" "$PROXY")
    fi
    
    if [[ -n "$CLIENT_CERT_P12" && -n "$CLIENT_CERT_P12_PASSWORD" ]]; then
        curl_cmd+=("--cert" "$CLIENT_CERT_P12:$CLIENT_CERT_P12_PASSWORD")
    fi
    
    curl_cmd+=("$url")
    
    "${curl_cmd[@]}"
    
    if [[ $? -ne 0 ]]; then
        return 1
    fi
    
    return 0
}

get_indexed_files() {
    local url="$1"
    local headers=("${@:2}")
    
    local tmp_file=$(mktemp)
    
    download_file "$url" "$tmp_file" "${headers[@]}"
    if [[ $? -ne 0 ]]; then
        rm -f "$tmp_file"
        return 1
    fi
    
    local files=()
    while read -r line; do
        if [[ "$line" =~ href=\"([^\"]+)\" ]]; then
            local href="${BASH_REMATCH[1]}"
            if [[ "$href" != "../" && "$href" != "/" && ! "$href" =~ ^[a-zA-Z]+:// && ! "$href" =~ ^// ]]; then
                if is_safe_path "$href"; then
                    files+=("$href")
                fi
            fi
        fi
    done < "$tmp_file"
    
    rm -f "$tmp_file"
    echo "${files[@]}"
}

sanitize_git_config() {
    local config_file="$1"
    
    if [[ ! -f "$config_file" ]]; then
        log_warning "Could not sanitize '$config_file', not a file."
        return
    fi
    
    sed -i.bak -E '/^\s*(fsmonitor|sshcommand|askpass|editor|pager|proxy)/Is/^/# /' "$config_file"
    rm -f "${config_file}.bak"
}

try_smart_http() {
    local url="$1"
    local dir="$2"
    
    log_info "Testing for 'smart' Git HTTP server..."
    
    local smart_url="${url}/.git/info/refs?service=git-upload-pack"
    local tmp_file=$(mktemp)
    
    download_file "$smart_url" "$tmp_file"
    if [[ $? -ne 0 ]]; then
        rm -f "$tmp_file"
        return 1
    fi
    
    local content_type=$(grep -i "^content-type:" "$tmp_file" | head -n 1 | tr -d '\r')
    local is_smart=0
    
    if [[ "$content_type" =~ application/x-git-upload-pack-advertisement ]] && \
       grep -q "# service=git-upload-pack" "$tmp_file"; then
        is_smart=1
    fi
    
    rm -f "$tmp_file"
    
    if [[ $is_smart -eq 1 ]]; then
        if command -v git >/dev/null; then
            log_info "Smart server detected. Using 'git clone' for faster download."
            if git clone --mirror "${url}/.git" "$dir"; then
                log_info "Mirror clone completed. Configuring for checkout."
                cd "$dir" || return 1
                sanitize_git_config "config"
                git config --bool core.bare false
                git reset --hard
                log_info "[+] Repository downloaded and restored in '$dir'."
                return 0
            else
                log_warning "'git clone' failed. Trying manual method."
            fi
        else
            log_warning "'git' not found in PATH. Trying manual method."
        fi
    else
        log_info "Not a smart server or git not available. Proceeding with manual method."
    fi
    
    return 1
}

download_git_directory() {
    local url="$1"
    local dir="$2"
    local headers=("${@:3}")
    
    log_info "Attempting to download .git directory recursively..."
    
    # Use wget for recursive download if available
    if command -v wget >/dev/null; then
        local wget_cmd=("wget" "-r" "-np" "-nH" "--cut-dirs=1" "-R" "index.html*" "--timeout=$TIMEOUT" "--tries=$RETRY")
        
        if [[ -n "$USER_AGENT" ]]; then
            wget_cmd+=("-U" "$USER_AGENT")
        fi
        
        for header in "${headers[@]}"; do
            wget_cmd+=("--header=$header")
        done
        
        if [[ -n "$PROXY" ]]; then
            wget_cmd+=("--proxy=on")
            # Convert proxy URL to wget format if needed
            # This is a simplified version - may need adjustment for different proxy types
            wget_cmd+=("--proxy=${PROXY}")
        fi
        
        wget_cmd+=("${url}/.git/" "-P" "$dir")
        
        if ! "${wget_cmd[@]}"; then
            log_warning "Recursive download with wget failed. Trying file-by-file method."
            return 1
        fi
        
        return 0
    else
        log_warning "wget not found. Cannot perform recursive download."
        return 1
    fi
}

download_git_manual() {
    local url="$1"
    local dir="$2"
    local headers=("${@:3}")
    
    log_info "Starting manual file-by-file download..."
    
    # Common Git files
    local common_files=(
        ".gitignore" ".git/COMMIT_EDITMSG" ".git/description"
        ".git/index" ".git/info/exclude" ".git/objects/info/packs"
        ".git/FETCH_HEAD" ".git/HEAD" ".git/ORIG_HEAD" 
        ".git/config" ".git/info/refs" ".git/packed-refs" 
        ".git/refs/stash" ".git/logs/HEAD" ".git/logs/refs/stash"
    )
    
    # Common branches
    local common_branches=("main" "master" "dev" "develop" "development" "staging" "test" "testing" "production" "release" "hotfix")
    
    # Add branch refs
    for branch in "${common_branches[@]}"; do
        common_files+=(".git/refs/heads/$branch")
        common_files+=(".git/refs/remotes/origin/$branch")
        common_files+=(".git/logs/refs/heads/$branch")
        common_files+=(".git/logs/refs/remotes/origin/$branch")
    done
    
    # Download common files
    for file in "${common_files[@]}"; do
        local output_path="${dir}/${file}"
        if [[ ! -f "$output_path" ]]; then
            log_info "Downloading $file..."
            download_file "${url}/${file}" "$output_path" "${headers[@]}"
        fi
    done
    
    # Process refs to find more files
    process_refs() {
        local ref_file="$1"
        if [[ ! -f "$ref_file" ]]; then
            return
        fi
        
        while read -r line; do
            if [[ "$line" =~ (refs(?:/[a-zA-Z0-9\-\.\_\*]+)+) ]]; then
                local ref="${BASH_REMATCH[1]}"
                if [[ ! "$ref" =~ \*$ ]] && is_safe_path "$ref"; then
                    local ref_path="${dir}/.git/${ref}"
                    local log_path="${dir}/.git/logs/${ref}"
                    
                    if [[ ! -f "$ref_path" ]]; then
                        log_info "Downloading .git/${ref}..."
                        download_file "${url}/.git/${ref}" "$ref_path" "${headers[@]}"
                    fi
                    
                    if [[ ! -f "$log_path" ]]; then
                        log_info "Downloading .git/logs/${ref}..."
                        download_file "${url}/.git/logs/${ref}" "$log_path" "${headers[@]}"
                    fi
                fi
            fi
        done < "$ref_file"
    }
    
    # Process refs files
    process_refs "${dir}/.git/FETCH_HEAD"
    process_refs "${dir}/.git/HEAD"
    process_refs "${dir}/.git/ORIG_HEAD"
    process_refs "${dir}/.git/packed-refs"
    process_refs "${dir}/.git/info/refs"
    
    # Download pack files if info/packs exists
    if [[ -f "${dir}/.git/objects/info/packs" ]]; then
        while read -r line; do
            if [[ "$line" =~ pack-([a-f0-9]{40})\.pack ]]; then
                local sha="${BASH_REMATCH[1]}"
                local idx_file=".git/objects/pack/pack-${sha}.idx"
                local pack_file=".git/objects/pack/pack-${sha}.pack"
                
                if [[ ! -f "${dir}/${idx_file}" ]]; then
                    log_info "Downloading $idx_file..."
                    download_file "${url}/${idx_file}" "${dir}/${idx_file}" "${headers[@]}"
                fi
                
                if [[ ! -f "${dir}/${pack_file}" ]]; then
                    log_info "Downloading $pack_file..."
                    download_file "${url}/${pack_file}" "${dir}/${pack_file}" "${headers[@]}"
                fi
            fi
        done < "${dir}/.git/objects/info/packs"
    fi
    
    # Git checkout
    log_info "Running 'git checkout .' to restore files..."
    cd "$dir" || return 1
    sanitize_git_config ".git/config"
    
    if ! git checkout .; then
        log_warning "git checkout failed. The repository may be incomplete."
        return 1
    fi
    
    return 0
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -j|--jobs)
                JOBS="$2"
                shift 2
                ;;
            -r|--retry)
                RETRY="$2"
                shift 2
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -u|--user-agent)
                USER_AGENT="$2"
                shift 2
                ;;
            -H|--header)
                HEADERS+=("$2")
                shift 2
                ;;
            --proxy)
                PROXY="$2"
                shift 2
                ;;
            --client-cert-p12)
                CLIENT_CERT_P12="$2"
                shift 2
                ;;
            --client-cert-p12-password)
                CLIENT_CERT_P12_PASSWORD="$2"
                shift 2
                ;;
            *)
                if [[ -z "$URL" ]]; then
                    URL="$1"
                elif [[ -z "$DIRECTORY" ]]; then
                    DIRECTORY="$1"
                else
                    log_error "Unexpected argument: $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # Validate arguments
    if [[ -z "$URL" || -z "$DIRECTORY" ]]; then
        log_error "Usage: $0 [options] URL DIRECTORY"
        exit 1
    fi
    
    if [[ "$JOBS" -lt 1 ]]; then
        log_error "Number of jobs must be >= 1"
        exit 1
    fi
    
    if [[ "$RETRY" -lt 1 ]]; then
        log_error "Number of retries must be >= 1"
        exit 1
    fi
    
    if [[ "$TIMEOUT" -lt 1 ]]; then
        log_error "Timeout must be >= 1"
        exit 1
    fi
    
    if [[ ! -d "$DIRECTORY" ]]; then
        mkdir -p "$DIRECTORY" || {
            log_error "Failed to create directory '$DIRECTORY'"
            exit 1
        }
    fi
    
    # Clean up URL
    URL="${URL%/}"
    if [[ "$URL" =~ /\.git$ ]]; then
        URL="${URL%/.git}"
    fi
    
    log_info "Testing for .git repository at: ${URL}/.git/"
    
    # Try smart HTTP first
    if try_smart_http "$URL" "$DIRECTORY"; then
        exit 0
    fi
    
    # Test for HEAD file
    local head_file=$(mktemp)
    if ! download_file "${URL}/.git/HEAD" "$head_file"; then
        log_error "Could not connect to ${URL}/.git/HEAD"
        rm -f "$head_file"
        exit 1
    fi
    
    if ! grep -qE "^(ref:.*|[0-9a-f]{40})" "$head_file"; then
        log_error "Invalid HEAD file content"
        rm -f "$head_file"
        exit 1
    fi
    
    rm -f "$head_file"
    
    # Try recursive directory download
    if download_git_directory "$URL" "$DIRECTORY" "${HEADERS[@]}"; then
        exit 0
    fi
    
    # Fall back to manual download
    if download_git_manual "$URL" "$DIRECTORY" "${HEADERS[@]}"; then
        log_info "Process completed. Repository downloaded to '$DIRECTORY'."
        exit 0
    else
        log_error "Failed to download repository"
        exit 1
    fi
}

main "$@"
