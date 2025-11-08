from .base import BaseClient
from typing import Dict, Any, Iterable, List, Optional
import datetime as dt
import re
import json
import time
import requests
from urllib.parse import urlparse, parse_qs

class TikiClient(BaseClient):
    def __init__(self, rate_per_min: int = 30, proxies: Optional[List[str]] = None, auth_header: Optional[str] = None):
        # Tiki có rate limit nghiêm ngặt hơn Shopee
        super().__init__(rate_per_min, proxies, auth_header)
        self.base_url = "https://tiki.vn"
        self.api_base = "https://tiki.vn/api/v2"
        
    def _extract_brand_id_from_url(self, brand_url: str) -> Optional[str]:
        """Extract brand ID from Tiki brand URL"""
        # https://tiki.vn/thuong-hieu/nan.html -> nan
        # https://tiki.vn/thuong-hieu/huggies.html -> huggies
        match = re.search(r'/thuong-hieu/([^./]+)', brand_url)
        if match:
            return match.group(1)
        return None
    
    def _extract_store_id_from_url(self, store_url: str) -> Optional[str]:
        """Extract store ID from Tiki store URL"""
        # https://tiki.vn/cua-hang/mrm-manlywear-official -> mrm-manlywear-official
        match = re.search(r'/cua-hang/([^/]+)', store_url)
        if match:
            return match.group(1)
        return None
    
    def _extract_category_id_from_url(self, category_url: str) -> Optional[str]:
        """Extract category ID from Tiki category URL"""
        # https://tiki.vn/thiet-bi-kts-phu-kien-so/c1815 -> 1815
        match = re.search(r'/c(\d+)', category_url)
        if match:
            return match.group(1)
        return None
    
    def _get_tiki_api_headers(self) -> Dict[str, str]:
        """Get headers for Tiki API calls"""
        headers = self._pick_headers()
        headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
            'Referer': 'https://tiki.vn/',
            'x-guest-token': 'K7ZFrL6EO8SZuOWGqxXbMvvqGXAoY4kV',  # Token cố định của Tiki
            'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        })
        return headers
    
    def get_products_by_brand(self, brand_name: str, limit: int = 48, page: int = 1) -> List[Dict[str, Any]]:
        """Get products by brand name using search"""
        url = f"{self.api_base}/products"
        
        # Improve search query for short brand names
        search_query = brand_name
        if len(brand_name) <= 3:
            # For short brand names like "nan", add more specific terms
            if brand_name.lower() == 'nan':
                search_query = 'nan optipro'  # NAN baby formula is usually OPTIPRO
            else:
                search_query = f"{brand_name} brand"
        
        params = {
            'limit': limit,
            'include': 'advertisement',
            'aggregations': '2',
            'q': search_query,
            'page': page,
            'sort': 'top_seller'
        }
        
        try:
            headers = self._get_tiki_api_headers()
            headers['Referer'] = f'https://tiki.vn/search?q={search_query.replace(" ", "+")}'
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Filter products that actually belong to the brand
            products = data.get('data', [])
            filtered_products = []
            
            for product in products:
                brand = product.get('brand', {})
                brand_name_product = product.get('brand_name', '').lower()
                brand_slug = brand.get('slug', '').lower() if brand else ''
                product_name = product.get('name', '').lower()
                
                # More precise brand matching
                brand_matches = (
                    brand_name_product == brand_name.lower() or
                    brand_slug == brand_name.lower() or
                    (len(brand_name) <= 3 and brand_name.lower() in brand_name_product) or
                    (len(brand_name) > 3 and brand_name.lower() in product_name)
                )
                
                if brand_matches:
                    filtered_products.append(product)
                    
                if len(filtered_products) >= limit:
                    break
            
            print(f"Found {len(filtered_products)} products for brand '{brand_name}' using query '{search_query}' (from {len(products)} total)")
            return filtered_products
            
        except Exception as e:
            print(f"Error getting products by brand {brand_name}: {e}")
            return []
    
    def get_products_by_store(self, store_id: str, limit: int = 48, page: int = 1) -> List[Dict[str, Any]]:
        """Get products by store ID"""
        url = f"{self.api_base}/products"
        params = {
            'limit': limit,
            'seller_id': store_id,
            'page': page,
            'sort': 'top_seller'
        }
        
        try:
            response = self.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            print(f"Error getting products by store {store_id}: {e}")
            return []
    
    def get_category_info(self, category_id: str) -> Dict[str, Any]:
        """Get category information by ID"""
        url = f"{self.api_base}/categories/{category_id}"
        
        try:
            headers = self._get_tiki_api_headers()
            print(f"🔍 Fetching category info for {category_id} from {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            category_data = response.json()
            print(f"✅ Got category: {category_data.get('name', 'Unknown')}")
            return category_data
        except Exception as e:
            print(f"❌ Error getting category info for {category_id}: {e}")
            return {"id": category_id, "name": "Unknown"}
    
    def get_products_by_category(self, category_id: str, limit: int = 48, page: int = 1) -> List[Dict[str, Any]]:
        """Get products by category ID"""
        url = f"{self.api_base}/products"
        params = {
            'limit': limit,
            'include': 'advertisement',
            'aggregations': '2',
            'category': category_id,
            'page': page,
            'sort': 'top_seller'
        }
        
        try:
            headers = self._get_tiki_api_headers()
            headers['Referer'] = f'https://tiki.vn/c{category_id}'
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            products = data.get('data', [])
            print(f"Found {len(products)} products in category {category_id}")
            return products
            
        except Exception as e:
            print(f"Error getting products by category {category_id}: {e}")
            return []
    
    def get_product_reviews(self, product_id: str, limit: int = 50, page: int = 1, sort: str = 'newest') -> List[Dict[str, Any]]:
        """Get reviews for a specific product with pagination support"""
        all_reviews = []
        current_page = page
        max_per_page = 20  # Tiki API limit per page (reduced from 50 to 20)
        
        # If limit is high, use pagination to get all reviews
        if limit > max_per_page:
            pages_needed = (limit + max_per_page - 1) // max_per_page
            
            for page_num in range(current_page, current_page + pages_needed):
                page_limit = min(max_per_page, limit - len(all_reviews))
                if page_limit <= 0:
                    break
                    
                page_reviews = self._get_single_page_reviews(product_id, page_limit, page_num, sort)
                if not page_reviews:
                    break
                    
                all_reviews.extend(page_reviews)
                
                # Stop if we got fewer reviews than requested (no more pages)
                if len(page_reviews) < page_limit:
                    break
                    
                time.sleep(0.2)  # Rate limiting between pages
        else:
            all_reviews = self._get_single_page_reviews(product_id, limit, page, sort)
        
        print(f"Found {len(all_reviews)} reviews for product {product_id}")
        return all_reviews[:limit]  # Ensure we don't exceed the requested limit
    
    def _get_single_page_reviews(self, product_id: str, limit: int, page: int, sort: str) -> List[Dict[str, Any]]:
        """Get reviews for a single page"""
        url = f"{self.api_base}/reviews"
        params = {
            'product_id': product_id,
            'limit': limit,
            'page': page,
            'sort': sort,
            'include': 'comments,contribute_info,customer'
        }
        
        try:
            headers = self._get_tiki_api_headers()
            headers['Referer'] = f'https://tiki.vn/product-p{product_id}.html'
            
            # Add more specific headers
            headers.update({
                'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            })
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                reviews = data.get('data', [])
                total_count = data.get('paging', {}).get('total', 0)
                
                print(f"Page {page}: {len(reviews)} reviews (total available: {total_count})")
                return reviews
            else:
                print(f"Error {response.status_code} getting reviews page {page} for product {product_id}")
                print(f"Response: {response.text[:200]}")
                return []
            
        except Exception as e:
            print(f"Exception getting reviews page {page} for product {product_id}: {e}")
            return []
    
    def crawl_brand_reviews(self, brand_url: str, max_products: int = 100, max_reviews_per_product: int = 20, days_back: int = 365) -> Iterable[Dict[str, Any]]:
        """Crawl reviews from brand products"""
        brand_name = self._extract_brand_id_from_url(brand_url)
        if not brand_name:
            print(f"Cannot extract brand name from URL: {brand_url}")
            return
        
        print(f"🏷️ Crawling reviews for brand: {brand_name}")
        products_collected = 0
        page = 1
        
        while products_collected < max_products:
            remaining = max_products - products_collected
            limit = min(48, remaining)  # Tiki API limit per page
            
            products = self.get_products_by_brand(brand_name, limit=limit, page=page)
            if not products:
                break
            
            for product in products:
                if products_collected >= max_products:
                    break
                
                product_id = str(product.get('id'))
                product_name = product.get('name', '')
                
                print(f"  📦 Getting reviews for product: {product_name[:50]}...")
                
                # Get reviews for this product
                reviews = self.get_product_reviews(product_id, limit=max_reviews_per_product)
                
                for review in reviews:
                    # Convert Tiki review format to standard format
                    review_data = self._convert_tiki_review(review, product, 'brand', brand_name)
                    if review_data and self._is_recent_review(review_data, days_back):
                        yield review_data
                
                products_collected += 1
                time.sleep(0.5)  # Extra delay between products
            
            page += 1
            if len(products) < limit:
                break
    
    def crawl_store_reviews(self, store_url: str, max_products: int = 100, max_reviews_per_product: int = 20, days_back: int = 365) -> Iterable[Dict[str, Any]]:
        """Crawl reviews from store products"""
        store_id = self._extract_store_id_from_url(store_url)
        if not store_id:
            print(f"Cannot extract store ID from URL: {store_url}")
            return
        
        print(f"🏪 Crawling reviews for store: {store_id}")
        products_collected = 0
        page = 1
        
        while products_collected < max_products:
            remaining = max_products - products_collected
            limit = min(48, remaining)
            
            products = self.get_products_by_store(store_id, limit=limit, page=page)
            if not products:
                break
            
            for product in products:
                if products_collected >= max_products:
                    break
                
                product_id = str(product.get('id'))
                product_name = product.get('name', '')
                
                print(f"  📦 Getting reviews for product: {product_name[:50]}...")
                
                reviews = self.get_product_reviews(product_id, limit=max_reviews_per_product)
                
                for review in reviews:
                    review_data = self._convert_tiki_review(review, product, 'store', store_id)
                    if review_data and self._is_recent_review(review_data, days_back):
                        yield review_data
                
                products_collected += 1
                time.sleep(0.5)
            
            page += 1
            if len(products) < limit:
                break
    
    def crawl_category_reviews(self, category_url: str, max_products: int = 100, max_reviews_per_product: int = 20, days_back: int = 365) -> Iterable[Dict[str, Any]]:
        """Crawl reviews from category products"""
        category_id = self._extract_category_id_from_url(category_url)
        if not category_id:
            print(f"Cannot extract category ID from URL: {category_url}")
            return
        
        # Get category information
        print(f"🔍 About to fetch category info for: {category_id}")
        category_info = self.get_category_info(category_id)
        category_name = category_info.get("name", "Unknown")
        print(f"📂 Crawling reviews for category: {category_id} ({category_name})")
        print(f"📋 Category info: {category_info}")
        products_collected = 0
        page = 1
        
        while products_collected < max_products:
            remaining = max_products - products_collected
            limit = min(48, remaining)
            
            products = self.get_products_by_category(category_id, limit=limit, page=page)
            if not products:
                break
            
            for product in products:
                if products_collected >= max_products:
                    break
                
                product_id = str(product.get('id'))
                product_name = product.get('name', '')
                
                print(f"  📦 Getting reviews for product: {product_name[:50]}...")
                
                reviews = self.get_product_reviews(product_id, limit=max_reviews_per_product)
                
                for review in reviews:
                    review_data = self._convert_tiki_review(review, product, 'category', category_id, category_name)
                    if review_data and self._is_recent_review(review_data, days_back):
                        yield review_data
                
                products_collected += 1
                time.sleep(0.5)
            
            page += 1
            if len(products) < limit:
                break
    
    def _convert_tiki_review(self, review: Dict[str, Any], product: Dict[str, Any], source_type: str, source_id: str, category_name: str = None) -> Optional[Dict[str, Any]]:
        """Convert Tiki review format to standard format"""
        try:
            # Extract review data
            review_id = review.get('id')
            rating = review.get('rating', 0)
            title = review.get('title', '')
            content = review.get('content', '')
            created_at = review.get('created_at', '')
            
            # Customer info
            created_by = review.get('created_by', {})
            reviewer_name = created_by.get('name', 'Anonymous')
            
            # Product info
            product_id = str(product.get('id', ''))
            product_name = product.get('name', '')
            
            # Category info - handle different category structures
            categories = product.get('categories', {})
            
            # Use provided category_name if available (from API call)
            if category_name and source_type == 'category':
                category_id = source_id
                resolved_category_name = category_name
            # Extract from product data if no category_name provided
            elif isinstance(categories, dict) and categories:
                if 'id' in categories:
                    category_id = str(categories['id'])
                    resolved_category_name = categories.get('name', 'Unknown')
                else:
                    resolved_category_name = 'Unknown'
            elif isinstance(categories, list) and categories:
                # If categories is a list, take the first one
                first_cat = categories[0] if categories else {}
                if isinstance(first_cat, dict):
                    category_id = str(first_cat.get('id', 'unknown'))
                    resolved_category_name = first_cat.get('name', 'Unknown')
                else:
                    resolved_category_name = 'Unknown'
            else:
                # No category information available
                category_id = source_id if source_type == 'category' else 'unknown'
                resolved_category_name = 'Unknown'
            
            # Construct product URL
            product_url = f"https://tiki.vn/product-p{product_id}.html" if product_id else ''
            
            return {
                'platform': 'tiki',
                'review_id': str(review_id) if review_id else '',
                'product_id': str(product_id) if product_id else '',
                'product_name': str(product_name) if product_name else '',
                'product_url': str(product_url),
                'category_id': str(category_id),
                'category_name': str(resolved_category_name),
                'rating': int(rating) if rating else 0,
                'title': str(title) if title else '',
                'content': str(content) if content else '',
                'reviewer_name': str(reviewer_name) if reviewer_name else 'Anonymous',
                'create_time': str(created_at) if created_at else '',
                'crawled_at': float(time.time()),
                'source_type': str(source_type),  # brand, store, category
                'source_id': str(source_id)
            }
        except Exception as e:
            print(f"Error converting Tiki review: {e}")
            return None
    
    def _is_recent_review(self, review_data: Dict[str, Any], days_back: int) -> bool:
        """Check if review is within the specified days_back period"""
        try:
            created_at = review_data.get('create_time', '')
            if not created_at:
                return True  # Include if no date info
            
            # Parse Tiki datetime format
            from datetime import datetime, timedelta
            
            if isinstance(created_at, str):
                # Try to parse ISO format or other common formats
                try:
                    review_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except:
                    # Fallback: assume recent if can't parse
                    return True
            else:
                return True
            
            cutoff_date = datetime.now() - timedelta(days=days_back)
            return review_date >= cutoff_date
            
        except Exception as e:
            print(f"Error checking review date: {e}")
            return True  # Include if error parsing date

    def crawl_reviews_from_url(self, url: str, max_products: int = 100, max_reviews_per_product: int = 20, days_back: int = 365) -> Iterable[Dict[str, Any]]:
        """Auto-detect URL type and crawl reviews accordingly"""
        if '/thuong-hieu/' in url:
            return self.crawl_brand_reviews(url, max_products, max_reviews_per_product, days_back)
        elif '/cua-hang/' in url:
            return self.crawl_store_reviews(url, max_products, max_reviews_per_product, days_back)
        elif '/c' in url and url.endswith(url.split('/c')[-1]):
            return self.crawl_category_reviews(url, max_products, max_reviews_per_product, days_back)
        else:
            print(f"❌ Unsupported Tiki URL format: {url}")
            print("✅ Supported formats:")
            print("   - Brand: https://tiki.vn/thuong-hieu/brand-name.html")
            print("   - Store: https://tiki.vn/cua-hang/store-name")
            print("   - Category: https://tiki.vn/category-name/c1234")
            return []