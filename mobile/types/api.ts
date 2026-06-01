export interface KeywordMapping {
  refined_tw_keyword: string;
  refined_jp_keyword: string;
  category: string;
}

export interface PriceListing {
  platform: string;
  title: string;
  price: number;
  currency: 'TWD' | 'JPY';
  url: string;
  image_url?: string | null;
}

export interface ProsCons {
  pros: string[];
  cons: string[];
}

export interface BuyingAdvice {
  price_comparison_summary: string;
  best_deal_location: 'Taiwan' | 'Japan' | 'Similar';
  tw_average_price_twd: number | null;
  jp_average_price_twd: number | null;
  jp_tax_free_price_twd: number | null;
  pros_cons: ProsCons;
  verdict: string;
}

export interface SearchResponse {
  keyword_mapping: KeywordMapping;
  tw_listings: PriceListing[];
  jp_listings: PriceListing[];
  exchange_rate_jpy_twd: number;
  advice: BuyingAdvice;
}
