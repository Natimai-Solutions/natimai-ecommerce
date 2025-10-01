"""
AI-powered product search agent for e-commerce platform.

This module provides natural language search capabilities for products,
allowing users to search using conversational queries like:
- "Show me wireless headphones under $100"
- "I need a comfortable office chair"
- "Find electronics on sale"

Setup Instructions:
1. Add OpenAI client dependency (AIDep) to app/api/deps.py
2. Add Redis client dependency (RedisDep) to app/api/deps.py
3. Ensure product models and CRUD are properly imported
4. Configure OpenAI API key in your settings

Example usage in your main router:
    from app.services.ia_search_agent import router as ai_search_router
    app.include_router(ai_search_router, prefix="/api/v1/ai-search", tags=["AI Search"])
"""

import json
import pickle
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import SessionDep

router = APIRouter()

# ============================================================================
# TYPE DEFINITIONS AND DEPENDENCIES
# ============================================================================

# TODO: Replace these with actual dependencies from app/api/deps.py
AIDep = Any  # Replace with actual OpenAI client type
RedisDep = Any  # Replace with actual Redis client type


# TODO: Import actual product models and replace these placeholders
class ProductPublic(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    base_price: float
    category_id: UUID | None = None


class Product(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    base_price: float
    category_id: UUID | None = None
    category: dict | None = None


class MockCrudProduct:
    async def get_multi(self, session: AsyncSession, limit: int = 100):
        return []  # Replace with actual CRUD implementation


crud_product = MockCrudProduct()

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class ProductSearchQuery(BaseModel):
    """Model for product search queries."""

    query: str = Field(description="Natural language search query")
    category: str | None = Field(
        default=None, description="Optional category filter"
    )
    min_price: float | None = Field(default=None, description="Minimum price filter")
    max_price: float | None = Field(default=None, description="Maximum price filter")
    limit: int = Field(default=10, description="Maximum number of results")


class ProductSearchResult(BaseModel):
    """Model for product search results."""

    products: list[ProductPublic] = Field(description="List of matching products")
    total_count: int = Field(description="Total number of matching products")
    search_explanation: str = Field(description="AI explanation of the search results")
    suggestions: list[str] = Field(
        default_factory=list, description="Search suggestions"
    )


class AIProductSearchResponse(BaseModel):
    """Response model for AI product search."""

    id: UUID = Field(description="Conversation ID")
    query: str = Field(description="Original search query")
    results: ProductSearchResult = Field(description="Search results")
    ai_message: str = Field(description="AI assistant response")


@router.post("/search", response_model=AIProductSearchResponse)
async def ai_product_search(
    query: ProductSearchQuery,
    session: SessionDep,
    conversation_id: UUID | None = None,
) -> AIProductSearchResponse:
    """
    AI-powered natural language product search.

    Examples:
    - "Show me wireless headphones under $100"
    - "I need a comfortable office chair"
    - "Find electronics on sale"
    """

    if conversation_id is None:
        conversation_id = uuid4()

    try:
        # Simple search implementation (replace with AI logic)
        search_terms = query.query.lower().split()

        # Mock search results
        mock_products = [
            ProductPublic(
                id=uuid4(),
                name="Example Product",
                description="This is a sample product",
                base_price=99.99,
                category_id=uuid4(),
            )
        ]

        results = ProductSearchResult(
            products=mock_products,
            total_count=1,
            search_explanation=f"Found products matching '{query.query}'",
            suggestions=["Try more specific terms", "Browse categories"],
        )

        return AIProductSearchResponse(
            id=conversation_id,
            query=query.query,
            results=results,
            ai_message=f"I found some products for your search: {query.query}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AI Product Search Agent"}


class ProductSearchQuery(BaseModel):
    """Model for product search queries."""

    query: str = Field(description="Natural language search query")
    category: str | None = Field(
        default=None, description="Optional category filter"
    )
    min_price: float | None = Field(default=None, description="Minimum price filter")
    max_price: float | None = Field(default=None, description="Maximum price filter")
    limit: int = Field(default=10, description="Maximum number of results")


class ProductSearchResult(BaseModel):
    """Model for product search results."""

    products: list[ProductPublic] = Field(description="List of matching products")
    total_count: int = Field(description="Total number of matching products")
    search_explanation: str = Field(description="AI explanation of the search results")
    suggestions: list[str] = Field(
        default_factory=list, description="Search suggestions"
    )


class AIProductSearchResponse(BaseModel):
    """Response model for AI product search."""

    id: UUID = Field(description="Conversation ID")
    query: str = Field(description="Original search query")
    results: ProductSearchResult = Field(description="Search results")
    ai_message: str = Field(description="AI assistant response")


async def get_product_context(session: AsyncSession) -> str:
    """Get contextual information about available products and categories."""

    # Get sample products and categories for context
    products = await crud_product.get_multi(session, limit=20)

    # Extract unique categories
    categories = set()
    product_examples = []

    for product in products:
        if product.category:
            categories.add(product.category.name)

        product_examples.append(
            {
                "name": product.name,
                "description": product.description,
                "price": product.base_price,
                "category": product.category.name
                if product.category
                else "Uncategorized",
            }
        )

    context = f"""
Database Context:
- Available Categories: {", ".join(sorted(categories)) if categories else "None"}
- Sample Products: {json.dumps(product_examples[:10], indent=2)}
- Total Products Available: {len(products)}

Search Capabilities:
- Product name matching
- Description search
- Category filtering  
- Price range filtering
- Fuzzy matching for typos
"""

    return context


async def parse_search_intent(
    ai_client: AIDep, user_query: str, context: str
) -> dict[str, Any]:
    """Use AI to parse user search intent into structured parameters."""

    system_prompt = f"""
You are a product search assistant for an e-commerce platform. 
Analyze the user's natural language query and extract search parameters.

{context}

Extract from the user query:
1. Main search terms (product name, features, etc.)
2. Category if mentioned
3. Price range if mentioned  
4. Any other relevant filters

Respond with a JSON object containing:
{{
    "search_terms": ["term1", "term2"],
    "category": "category_name or null",
    "min_price": number or null,
    "max_price": number or null,
    "intent": "brief description of what user is looking for"
}}

Be flexible with category names and product terms. Use fuzzy matching logic.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Search query: {user_query}"},
    ]

    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,  # Low temperature for consistent parsing
        )

        ai_response = response.choices[0].message.content
        # Extract JSON from the response
        start = ai_response.find("{")
        end = ai_response.rfind("}") + 1
        json_str = (
            ai_response[start:end] if start != -1 and end > start else ai_response
        )

        return json.loads(json_str)

    except (json.JSONDecodeError, Exception):
        # Fallback: simple keyword extraction
        return {
            "search_terms": user_query.split(),
            "category": None,
            "min_price": None,
            "max_price": None,
            "intent": f"Search for: {user_query}",
        }


async def search_products_with_ai_filters(
    session: AsyncSession, search_intent: dict[str, Any]
) -> list[Product]:
    """Search products using AI-parsed filters."""

    # Start with all active products
    products = await crud_product.get_multi(
        session, limit=1000
    )  # Get more for filtering

    search_terms = search_intent.get("search_terms", [])
    category_filter = search_intent.get("category")
    min_price = search_intent.get("min_price")
    max_price = search_intent.get("max_price")

    filtered_products = []

    for product in products:
        # Score each product based on relevance
        score = 0

        # Name matching (highest priority)
        product_name_lower = product.name.lower()
        for term in search_terms:
            term_lower = term.lower()
            if term_lower in product_name_lower:
                score += 10
            elif any(term_lower in word for word in product_name_lower.split()):
                score += 5

        # Description matching
        if product.description:
            desc_lower = product.description.lower()
            for term in search_terms:
                term_lower = term.lower()
                if term_lower in desc_lower:
                    score += 3

        # Category matching
        if category_filter and product.category:
            if category_filter.lower() in product.category.name.lower():
                score += 8

        # Price filtering
        price_match = True
        if min_price and product.base_price < min_price:
            price_match = False
        if max_price and product.base_price > max_price:
            price_match = False

        # Only include products that match price filters and have some relevance
        if price_match and (score > 0 or not search_terms):
            filtered_products.append((product, score))

    # Sort by relevance score (descending)
    filtered_products.sort(key=lambda x: x[1], reverse=True)

    return [product for product, score in filtered_products]


async def generate_search_explanation(
    ai_client: AIDep,
    user_query: str,
    search_intent: dict[str, Any],
    products: list[Product],
) -> tuple[str, list[str]]:
    """Generate AI explanation of search results and suggestions."""

    results_summary = f"""
Found {len(products)} products matching your search.
Search Intent: {search_intent.get("intent", "General search")}
Filters applied: 
- Search terms: {", ".join(search_intent.get("search_terms", []))}
- Category: {search_intent.get("category", "Any")}
- Price range: {search_intent.get("min_price", "No min")} - {search_intent.get("max_price", "No max")}

Top Results:
"""

    for i, product in enumerate(products[:5]):  # Show top 5
        results_summary += f"{i + 1}. {product.name} - ${product.base_price}"
        if product.category:
            results_summary += f" (Category: {product.category.name})"
        results_summary += "\n"

    system_prompt = """
You are a helpful e-commerce search assistant. 
Analyze the search results and provide:
1. A friendly explanation of what was found
2. Helpful suggestions for refining the search

Be conversational and helpful. If few results were found, suggest alternatives.
If many results were found, suggest ways to narrow down the search.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"User searched for: '{user_query}'\n\nResults:\n{results_summary}",
        },
    ]

    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o", messages=messages, temperature=0.7
        )

        explanation = response.choices[0].message.content

        # Generate simple suggestions based on results
        suggestions = []
        if len(products) > 10:
            suggestions.append("Try adding a category filter to narrow results")
            suggestions.append("Specify a price range to find products in your budget")
        elif len(products) < 5:
            suggestions.append("Try broader search terms")
            suggestions.append("Check spelling of product names")
            if search_intent.get("category"):
                suggestions.append("Try searching without category filter")

        return explanation, suggestions

    except Exception:
        # Fallback explanation
        explanation = f"I found {len(products)} products matching '{user_query}'. "
        if len(products) == 0:
            explanation += "Try using different search terms or browse by category."
        elif len(products) > 20:
            explanation += "Consider adding filters to narrow your search."
        else:
            explanation += "Here are the best matches for your query."

        return explanation, [
            "Try related keywords",
            "Browse by category",
            "Adjust price filters",
        ]


@router.post("/search", response_model=AIProductSearchResponse)
async def ai_product_search(
    query: ProductSearchQuery,
    session: SessionDep,
    ai_client: AIDep,
    redis: RedisDep,
    conversation_id: UUID = None,
) -> AIProductSearchResponse:
    """
    AI-powered natural language product search.

    This endpoint allows users to search for products using natural language queries.
    The AI assistant will parse the intent, search the database, and provide
    explanatory results with suggestions.

    Examples:
    - "Show me wireless headphones under $100"
    - "I need a comfortable office chair"
    - "Find electronics on sale"
    - "Red dress for a wedding"
    """

    if conversation_id is None:
        conversation_id = uuid4()

    try:
        # Get database context for AI
        context = await get_product_context(session)

        # Parse user intent with AI
        search_intent = await parse_search_intent(ai_client, query.query, context)

        # Override with explicit filters from query if provided
        if query.category:
            search_intent["category"] = query.category
        if query.min_price:
            search_intent["min_price"] = query.min_price
        if query.max_price:
            search_intent["max_price"] = query.max_price

        # Search products using AI-parsed filters
        matching_products = await search_products_with_ai_filters(
            session, search_intent
        )

        # Apply limit
        limited_products = matching_products[: query.limit]

        # Generate AI explanation and suggestions
        explanation, suggestions = await generate_search_explanation(
            ai_client, query.query, search_intent, matching_products
        )

        # Convert to public models
        public_products = [ProductPublic.model_validate(p) for p in limited_products]

        # Create search results
        results = ProductSearchResult(
            products=public_products,
            total_count=len(matching_products),
            search_explanation=explanation,
            suggestions=suggestions,
        )

        # Store conversation history
        history_key = f"ProductSearch-{conversation_id}"
        search_history = {
            "query": query.query,
            "intent": search_intent,
            "results_count": len(matching_products),
            "timestamp": str(datetime.utcnow()),
        }

        # Get existing history
        cached_history = await redis.get(history_key)
        if cached_history:
            history = pickle.loads(cached_history)
        else:
            history = []

        history.append(search_history)
        await redis.set(history_key, pickle.dumps(history), ex=3600)  # 1 hour expiry

        return AIProductSearchResponse(
            id=conversation_id,
            query=query.query,
            results=results,
            ai_message=explanation,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/search/suggestions")
async def get_search_suggestions(
    session: SessionDep, category: str | None = None
) -> dict[str, list[str]]:
    """
    Get search suggestions based on available products and categories.
    """

    try:
        # Get popular product categories and names for suggestions
        products = await crud_product.get_multi(session, limit=100)

        categories = set()
        product_names = []
        common_words = set()

        for product in products:
            if product.category:
                categories.add(product.category.name)

            product_names.append(product.name)

            # Extract common words from product names and descriptions
            name_words = product.name.lower().split()
            common_words.update(name_words)

            if product.description:
                desc_words = product.description.lower().split()
                common_words.update([w for w in desc_words if len(w) > 3])

        # Filter out very common words
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "they",
            "have",
            "been",
        }
        filtered_words = [w for w in common_words if w not in stopwords and len(w) > 2]

        return {
            "categories": sorted(list(categories)),
            "popular_terms": sorted(filtered_words)[:20],
            "example_queries": [
                f"Find {list(categories)[0] if categories else 'products'} under $50",
                "Show me the newest arrivals",
                "I need something for outdoor activities",
                "Budget-friendly electronics",
                "Premium quality items",
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get suggestions: {str(e)}"
        )
