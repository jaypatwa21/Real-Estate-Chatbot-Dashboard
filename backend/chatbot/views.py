import pandas as pd
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view
import os


@method_decorator(csrf_exempt, name='dispatch')
class QueryView(APIView):

    def post(self, request):
        query = request.data.get('query', '').lower()
        if not query:
            return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)

        # ------------------------------
        # LOAD & NORMALIZE DATA
        # ------------------------------
        file_path = os.path.join(settings.BASE_DIR, 'Sample_data.xlsx')

        try:
            df = pd.read_excel(file_path)
        except:
            return Response({'error': 'Data file not found'}, status=500)

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()

        # Rename Excel columns → chatbot standard names
        df = df.rename(columns={
            'final location': 'location',
            'year': 'year',
            'total_sales - igr': 'price',
            'total sold - igr': 'demand',
            'total units': 'supply'
        })

        # Validate required columns
        required_cols = ['location', 'year', 'price']
        for col in required_cols:
            if col not in df.columns:
                return Response(
                    {"error": f"Excel missing required column: {col}"},
                    status=500
                )

        # ------------------------------
        # PARSE QUERY
        # ------------------------------
        unique_locations = df['location'].astype(str).str.lower().unique()
        location_pattern = r'\b(' + '|'.join(unique_locations) + r')\b'

        locations = re.findall(location_pattern, query)
        years = re.findall(r'\b(20\d{2})\b', query)
        years = [int(y) for y in years] if years else None

        # Determine query type
        if "compare" in query or " vs " in query or "versus" in query:
            query_type = "compare"
        elif "trend" in query or "over" in query:
            query_type = "trend"
        else:
            query_type = "average"

        # ------------------------------
        # FILTER DATA
        # ------------------------------
        filtered_df = df.copy()

        if locations:
            filtered_df = filtered_df[filtered_df['location'].str.lower().isin(locations)]

        if years:
            filtered_df = filtered_df[filtered_df['year'].isin(years)]

        if filtered_df.empty:
            return Response({
                "summary": "No matching data found.",
                "chart_data": {},
                "table_data": []
            })

        # ------------------------------
        # SUMMARY & CHART GENERATION
        # ------------------------------
        summary = self.generate_summary(filtered_df, query_type, locations, years)
        chart_data = self.generate_chart_data(filtered_df, query_type, locations)

        # Prepare table output
        table_data = filtered_df.to_dict("records")

        return Response({
            "summary": summary,
            "chart_data": chart_data,
            "table_data": table_data
        })

    # =====================================================
    # SUMMARY LOGIC
    # =====================================================
    def generate_summary(self, df, query_type, locations, years):

        # ---------- AVERAGE ----------
        if query_type == "average":
            avg_price = df['price'].mean()
            loc = ", ".join(locations) if locations else "all locations"
            return f"Average price in {loc} is ₹{avg_price:,.2f}"

        # ---------- TREND ----------
        elif query_type == "trend":
            if len(locations) != 1:
                return "Trend requires exactly one location."

            loc = locations[0]
            loc_df = df[df['location'].str.lower() == loc].sort_values("year")

            if len(loc_df) < 2:
                return f"Not enough data to compute trend for {loc}"

            start = loc_df['price'].iloc[0]
            end = loc_df['price'].iloc[-1]
            change = ((end - start) / start) * 100

            return f"Prices in {loc} changed by {change:.2f}% over time."

        # ---------- COMPARE ----------
        elif query_type == "compare":
            if len(locations) != 2:
                return "Comparison requires exactly two locations."

            loc1, loc2 = locations
            avg1 = df[df['location'] == loc1]['price'].mean()
            avg2 = df[df['location'] == loc2]['price'].mean()

            diff = abs(avg1 - avg2)
            higher = loc1 if avg1 > avg2 else loc2

            return f"{higher} has a higher average price by ₹{diff:,.2f}"

        return "Unable to generate summary."

    # =====================================================
    # CHART LOGIC
    # =====================================================
    def generate_chart_data(self, df, query_type, locations):

        # ---------- TREND LINE CHART ----------
        if query_type == "trend" and len(locations) == 1:
            loc = locations[0]
            loc_df = df[df['location'].str.lower() == loc].sort_values("year")

            return {
                "labels": loc_df["year"].tolist(),
                "datasets": [{
                    "label": f"Price trend in {loc}",
                    "data": loc_df["price"].tolist(),
                    "borderColor": "rgba(54,162,235,1)",
                    "backgroundColor": "rgba(54,162,235,0.4)"
                }]
            }

        # ---------- COMPARE BAR CHART ----------
        if query_type == "compare" and len(locations) == 2:
            loc1, loc2 = locations
            avg1 = df[df['location'] == loc1]['price'].mean()
            avg2 = df[df['location'] == loc2]['price'].mean()

            return {
                "labels": [loc1, loc2],
                "datasets": [{
                    "label": "Average Price Comparison",
                    "data": [avg1, avg2],
                    "backgroundColor": ["rgba(255,99,132,0.5)", "rgba(54,162,235,0.5)"],
                    "borderColor": ["rgba(255,99,132,1)", "rgba(54,162,235,1)"],
                    "borderWidth": 1
                }]
            }

        # ---------- AVERAGE BAR CHART ----------
        avg_df = df.groupby("location")["price"].mean().reset_index()

        return {
            "labels": avg_df["location"].tolist(),
            "datasets": [{
                "label": "Average Price",
                "data": avg_df["price"].tolist(),
                "backgroundColor": "rgba(153,102,255,0.5)",
                "borderColor": "rgba(153,102,255,1)",
                "borderWidth": 1
            }]
        }


# ==========================================================
# FUNCTION WRAPPER (REQUIRED FOR URLS)
# ==========================================================
@api_view(["POST"])
def query_view(request):
    django_request = request._request
    view = QueryView.as_view()
    return view(django_request)
