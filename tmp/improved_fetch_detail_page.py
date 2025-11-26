    def fetch_detail_page(self, url: str) -> Dict:
        """
        Fetch and parse detail page to get accurate specifications and features
        
        Uses multi-tier extraction approach:
        1. JSON extraction (highest yield: 40-80+ features)
        2. HTML list parsing (moderate yield: 15-40 features)
        3. Meta tag extraction (fallback: 4-7 features)
        
        Args:
            url: Vehicle detail page URL
            
        Returns:
            Dictionary with scraped specifications and features list
        """
        specs = {}
        features = []
        
        try:
            self.logger.debug(f"Fetching detail page: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ============================================================
            # TIER 1: JSON EXTRACTION (Highest Priority)
            # ============================================================
            # VandenBrug uses Next.js, check for embedded JSON data
            json_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL)
            if json_match:
                try:
                    import json
                    data = json.loads(json_match.group(1))
                    
                    # Navigate JSON structure to find equipment/features
                    # Path may vary, try common patterns
                    try:
                        # Try path 1: props.pageProps.vehicle.equipment
                        vehicle_data = data.get('props', {}).get('pageProps', {}).get('vehicle', {})
                        equipment = vehicle_data.get('equipment', [])
                        if equipment:
                            if isinstance(equipment, list):
                                features.extend([str(item) for item in equipment if item])
                            elif isinstance(equipment, dict):
                                # Categorized equipment
                                for category, items in equipment.items():
                                    if isinstance(items, list):
                                        features.extend([str(item) for item in items if item])
                            self.logger.info(f"Extracted {len(features)} features from JSON (Tier 1)")
                    except (KeyError, AttributeError):
                        pass
                    
                    # Try alternative JSON paths if first didn't work
                    if not features:
                        try:
                            # Try path 2: props.pageProps.vehicleData.options
                            vehicle_data = data.get('props', {}).get('pageProps', {}).get('vehicleData', {})
                            options = vehicle_data.get('options', [])
                            if options:
                                features.extend([str(item) for item in options if item])
                                self.logger.info(f"Extracted {len(features)} features from JSON alternative path (Tier 1)")
                        except (KeyError, AttributeError):
                            pass
                    
                except json.JSONDecodeError as e:
                    self.logger.debug(f"JSON parsing failed: {e}")
                except Exception as e:
                    self.logger.debug(f"JSON extraction error: {e}")
            
            # ============================================================
            # TIER 2: HTML LIST PARSING (Medium Priority)
            # ============================================================
            # Only proceed if JSON extraction didn't yield results
            if not features or len(features) < 10:
                self.logger.debug("Trying HTML list parsing (Tier 2)")
                
                # Multiple selectors with Dutch terms
                feature_selectors = [
                    # Dutch-specific selectors
                    "ul[class*='uitrusting'] li",
                    "div[class*='uitrusting'] li",
                    "ul[class*='optie'] li",
                    "div[class*='optie'] li",
                    "[class*='standaard'] li",
                    "div[class*='extra'] li",
                    
                    # English selectors
                    "ul[class*='feature'] li",
                    "div[class*='equipment'] li",
                    "ul[class*='option'] li",
                    "[class*='features'] li",
                    
                    # Generic selectors (broader)
                    "section[class*='spec'] li",
                    "div[class*='spec'] li",
                ]
                
                for selector in feature_selectors:
                    feature_elems = soup.select(selector)
                    
                    # Only use if we found a meaningful section (more than 5 items)
                    if len(feature_elems) > 5:
                        html_features = []
                        for elem in feature_elems:
                            text = elem.get_text(strip=True)
                            # Filter: reasonable length, not just numbers
                            if text and 2 < len(text) < 100 and not text.isdigit():
                                html_features.append(text)
                        
                        if html_features:
                            features.extend(html_features)
                            self.logger.info(f"Extracted {len(html_features)} features from HTML lists with selector '{selector}' (Tier 2)")
                            break  # Found good results, stop trying selectors
                
                # Alternative approach: Look for section headings with Dutch terms
                if not features or len(features) < 10:
                    self.logger.debug("Trying section heading approach (Tier 2b)")
                    feature_headings = soup.find_all(['h2', 'h3', 'h4', 'h5'])
                    
                    for heading in feature_headings:
                        heading_text = heading.get_text().lower()
                        
                        # Dutch terms for equipment/features sections
                        if any(term in heading_text for term in ['uitrusting', 'standaard', 'opties', 'extra', 'features', 'equipment']):
                            # Look for list under this heading
                            next_ul = heading.find_next_sibling('ul')
                            if next_ul:
                                section_features = []
                                for li in next_ul.find_all('li'):
                                    feature_text = li.get_text(strip=True)
                                    if feature_text and 2 < len(feature_text) < 100:
                                        section_features.append(feature_text)
                                
                                if section_features:
                                    features.extend(section_features)
                                    self.logger.info(f"Extracted {len(section_features)} features from section '{heading_text}' (Tier 2b)")
                                    break
            
            # ============================================================
            # TIER 3: META TAG EXTRACTION (Fallback)
            # ============================================================
            # Only use if previous methods didn't yield good results
            if not features or len(features) < 10:
                self.logger.debug("Falling back to meta tag extraction (Tier 3)")
                
                # Extract features from title meta tag (pipe-separated)
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text(strip=True)
                    # Title format: "Make Model Edition | Feature1 | Feature2 | Feature3 | Dealer Name"
                    title_parts = [part.strip() for part in title_text.split('|')]
                    if len(title_parts) > 2:
                        # Skip first part (car name) and last part (dealer name)
                        title_features = title_parts[1:-1]
                        features.extend([f for f in title_features if f])
                        self.logger.debug(f"Extracted {len(title_features)} features from title (Tier 3)")
                
                # Extract features from description meta tag
                description_tag = soup.find('meta', {'name': 'description'})
                if description_tag:
                    description = description_tag.get('content', '')
                    # Look for pattern: "Verder is de [brand] uitgerust met: [features]"
                    uitgerust_match = re.search(r'uitgerust met:([^.]+)', description, re.IGNORECASE)
                    if uitgerust_match:
                        features_text = uitgerust_match.group(1).strip()
                        # Split by comma and clean up
                        desc_features = [f.strip() for f in features_text.split(',')]
                        # Also split "en" at the end (Dutch for "and")
                        final_features = []
                        for feature in desc_features:
                            if ' en ' in feature:
                                # Split on "en" to get the last feature
                                parts = [p.strip() for p in feature.split(' en ')]
                                final_features.extend([p for p in parts if p])
                            else:
                                final_features.append(feature)
                        features.extend([f for f in final_features if f])
                        self.logger.debug(f"Extracted {len(final_features)} features from description (Tier 3)")
            
            # ============================================================
            # POST-PROCESSING: Remove duplicates
            # ============================================================
            seen = set()
            unique_features = []
            for feature in features:
                feature_lower = feature.lower()
                if feature_lower not in seen and feature:
                    seen.add(feature_lower)
                    unique_features.append(feature)
            
            specs['features'] = unique_features
            self.logger.info(f"Total unique features extracted: {len(unique_features)}")
            
            # ============================================================
            # SPECIFICATION EXTRACTION (Unchanged)
            # ============================================================
            # Find specifications section
            spec_items = soup.find_all('div', class_='BlockVehicleSpecs_spec__Gz_Qg')
            
            for spec_div in spec_items:
                spans = spec_div.find_all('span')
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    value = spans[1].get_text(strip=True)
                    
                    # Map Dutch labels to our keys
                    if label == 'Brandstof':
                        specs['fuel'] = value
                    elif label == 'Kilometerstand':
                        # Extract just the number
                        km_match = re.search(r'([\d.]+)', value.replace('.', ''))
                        if km_match:
                            specs['mileage_km'] = int(km_match.group(1))
                    elif label == 'Bouwjaar':
                        specs['year'] = int(value)
                    elif label == 'Transmissie':
                        specs['transmission'] = value
                    elif label == 'Vermogen (pk)':
                        pk_match = re.search(r'(\d+)', value)
                        if pk_match:
                            specs['power_pk'] = int(pk_match.group(1))
                    elif label == 'Kenteken':
                        specs['license_plate'] = value
                        
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            self.logger.warning(f"Error fetching detail page {url}: {e}")
        
        return specs
