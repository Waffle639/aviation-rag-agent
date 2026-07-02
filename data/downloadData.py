import requests
import os
import re
import time


class DataDownloader:
    """Simple class to download files from URLs."""

    wikipedia_headers = {
        "User-Agent": "aviation-rag-agent/1.0 (contact: local-dev)"
    }
    wikipedia_retry_delay = 5
    wikipedia_max_retries = 5
    wikipedia_pause_between_titles = 1

    
    def __init__(self, carpeta_salida="data/raw/"):
        self.carpeta_salida = carpeta_salida
        # Create folder if it doesn't exist
        if not os.path.exists(carpeta_salida):
            os.makedirs(carpeta_salida)
    
    def descargar(self, url):
        """Download a single file from a URL."""
        # Get filename from URL
        nombre_archivo = url.split('/')[-1]
        ruta_completa = os.path.join(self.carpeta_salida, nombre_archivo)
        
        
        try:
            respuesta = requests.get(url)
            
            if os.path.exists(ruta_completa):
                print(f"File already exists: {ruta_completa}")
                return True
            
            if respuesta.status_code == 200:
                # Save the file
                with open(ruta_completa, 'wb') as archivo:
                    archivo.write(respuesta.content)
                print(f"Success: Saved to {ruta_completa}")
                return True
            else:
                print(f"Error: Status code {respuesta.status_code}")
                return False    
        
        except Exception as e:
            print(f"Error: {e}\n")
            
        
    
    def download_multiple(self, urls):
        """Download multiple files from a list."""
        total_urls = len(urls)
        successful_downloads = 0
        failed_downloads = 0
        for url in urls:
            if self.descargar(url):
                successful_downloads += 1
            else:
                failed_downloads += 1
        print(f"Download completed: {successful_downloads} successful, {failed_downloads} failed out of {total_urls} URLs.")
        
        
    
    def download_wikipedia_extract(self, title, idioma="en"):
        """Download a Wikipedia extract and save it as a text file."""
        wiki_dir = os.path.join(self.carpeta_salida, "wiki")
        os.makedirs(wiki_dir, exist_ok=True)

        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")
        file_path = os.path.join(wiki_dir, f"{safe_title}.txt")

        for attempt in range(1, self.wikipedia_max_retries + 1):
            if os.path.exists(file_path):
                print(f"Wikipedia extract already exists: {file_path}")
                return True
            try:
                response = requests.get(
                    f"https://{idioma}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "prop": "extracts",
                        "titles": title,
                        "format": "json",
                        "explaintext": True,
                    },
                    headers=self.wikipedia_headers,
                    timeout=30,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else self.wikipedia_retry_delay * attempt
                    print(f"Too many requests for '{title}'. Waiting {wait_seconds}s before retry {attempt}/{self.wikipedia_max_retries}.")
                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()

                data = response.json()
                pages = data["query"]["pages"]
                extract = next(iter(pages.values())).get("extract", "")

                with open(file_path, "w", encoding="utf-8") as file:
                    file.write(extract)

                print(f"Saved Wikipedia extract to {file_path}")
                time.sleep(self.wikipedia_pause_between_titles)
                return True

            except Exception as e:
                if attempt == self.wikipedia_max_retries:
                    print(f"Error downloading Wikipedia page '{title}': {e}")
                    return False

                wait_seconds = self.wikipedia_retry_delay * attempt
                print(f"Error downloading '{title}' on attempt {attempt}/{self.wikipedia_max_retries}: {e}. Retrying in {wait_seconds}s.")
                time.sleep(wait_seconds)

        return False

    def download_wikipedia_extracts(self, titles, idioma="en"):
        """Download multiple Wikipedia extracts into data/raw/wiki."""
        total_titles = len(titles)
        successful_downloads = 0
        failed_downloads = 0

        for title in titles:
            if self.download_wikipedia_extract(title, idioma):
                successful_downloads += 1
            else:
                failed_downloads += 1

        print(
            f"Wikipedia download completed: {successful_downloads} successful, {failed_downloads} failed out of {total_titles} titles."
        )




# Example usage
if __name__ == "__main__":
    # Create downloader
    downloader = DataDownloader()

    urls = ["https://www.boeing.com/content/dam/boeing/v2/airports/acaps/707.pdf",
            "https://www.boeing.com/content/dam/boeing/v2/airports/acaps/747-400_Rev_F.pdf",
            "https://www.boeing.com/content/dam/boeing/boeingdotcom/commercial/airports/acaps/748_REV_C.pdf",
            "https://www.aircraft.airbus.com/sites/g/files/jlcbta126/files/2023-08/ac_a330_jul2023_0.pdf",
            "https://www.aircraft.airbus.com/sites/g/files/jlcbta126/files/2025-01/AC_A320_0624.pdf",
            "https://www.congress.gov/crs_external_products/IF/PDF/IF12945/IF12945.7.pdf",
    ]
            

    wiki_planes_titles = [
    "Boeing 747",
    "Boeing 747-8",
    "Airbus A330",
    "Airbus A320 family",
    "Lockheed Martin F-22 Raptor",
    "Lockheed Martin F-35 Lightning II",
    "Chengdu J-20",
    "Sukhoi Su-57",
    "McDonnell Douglas F-15 Eagle",
    "McDonnell Douglas F/A-18 Hornet",
    "General Dynamics F-16 Fighting Falcon",
    "Mikoyan MiG-29",
    "Sukhoi Su-27",
    "Eurofighter Typhoon",
    "Northrop Grumman B-2 Spirit",
    "Saab 35 Draken",
    "Sukhoi Su-47",
    ]
    
    downloader.download_multiple(urls)
    downloader.download_wikipedia_extracts(wiki_planes_titles, idioma="en")
