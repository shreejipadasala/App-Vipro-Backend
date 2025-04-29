import pandas as pd
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO
from rest_framework.response import Response
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from .models import UploadedFile
from .serializers import FileSerializer
from mplfinance.original_flavor import candlestick_ohlc
import matplotlib.dates as mdates
import numpy as np
# from django.views.generic import TemplateView
from django.views.generic import View
from django.http import HttpResponse, JsonResponse
import os
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token

uploaded_data = None  

# def index(request):
#     return render(request, 'index.html')

@api_view(['GET','POST'])
def csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})

@api_view(['GET', 'POST'])
@csrf_exempt
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    global uploaded_data

    if request.method == 'GET':
        return Response({
            "error": "GET method is not supported on this endpoint. Please use POST to upload a file."
        }, status=405)

    if 'file' not in request.data:
        return Response({"error": "No file provided"}, status=400)

    serializer = FileSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        file_instance = serializer.instance
        file_path = file_instance.file.path

        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith('.json'):
                df = pd.read_json(file_path)
            else:
                return Response({"error": "Unsupported file format"}, status=400)
            
            uploaded_data = df
            categories = df.columns.tolist()

            return Response({
                "message": "File uploaded successfully",
                "categories": categories
            }, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    return Response(serializer.errors, status=400)

@api_view(['POST'])
@csrf_exempt
def get_recommendations(request):
    """Analyze data and suggest appropriate chart types"""
    global uploaded_data
    
    if uploaded_data is None:
        return Response({"error": "No data uploaded yet"}, status=400)

    columns = request.data.get('columns', [])
    if not columns:
        return Response({"error": "No columns provided for analysis"}, status=400)
    
    try:
        recommendations = analyze_data_for_recommendations(uploaded_data, columns)
        return Response({"recommendations": recommendations})
    except Exception as e:
        return Response({"error": str(e)}, status=500)

def analyze_data_for_recommendations(df, columns):
    """Analyze the dataframe to suggest chart types"""
    recommendations = []
    
    col_info = {}
    for col in columns:
        if col in df.columns:
            dtype = str(df[col].dtype)
            if dtype.startswith('datetime'):
                col_type = 'datetime'
            elif dtype in ['int64', 'float64']:
                col_type = 'numeric'
                unique_vals = df[col].nunique()
                is_temporal = False
                try:
                    if pd.api.types.is_numeric_dtype(df[col]):
                        if (df[col] > 1900).all() and (df[col] < 2100).all():
                            is_temporal = True
                except:
                    pass
            else:
                col_type = 'categorical'
                unique_vals = df[col].nunique()
            
            col_info[col] = {
                'type': col_type,
                'unique_values': unique_vals if col_type != 'datetime' else None,
                'is_temporal': is_temporal if col_type == 'numeric' else False
            }
    
    num_numeric = sum(1 for info in col_info.values() if info['type'] == 'numeric')
    num_categorical = sum(1 for info in col_info.values() if info['type'] == 'categorical')
    num_datetime = sum(1 for info in col_info.values() if info['type'] == 'datetime')
    
    if num_datetime >= 1 and num_numeric >= 1:
        recommendations.append({"type": "line", "confidence": 0.95})
        recommendations.append({"type": "area", "confidence": 0.85})
    
    if num_categorical >= 1 and num_numeric >= 1:
        recommendations.append({"type": "bar", "confidence": 0.90})
        if num_categorical == 1 and num_numeric == 1:
            recommendations.append({"type": "pie", "confidence": 0.75})
            recommendations.append({"type": "sunburst", "confidence": 0.65})
    
    if num_numeric >= 2:
        recommendations.append({"type": "scatter", "confidence": 0.85})
    
    if num_numeric >= 1:
        recommendations.append({"type": "histogram", "confidence": 0.80})
        recommendations.append({"type": "box", "confidence": 0.75})
        recommendations.append({"type": "violin", "confidence": 0.70})
    
    if num_numeric >= 4 and num_datetime >= 1:
        recommendations.append({"type": "stock", "confidence": 0.85})
    
    if num_categorical >= 1 and num_numeric == 1:
        recommendations.append({"type": "funnel", "confidence": 0.70})
    
    seen = set()
    unique_recommendations = []
    for r in recommendations:
        if r['type'] not in seen:
            seen.add(r['type'])
            unique_recommendations.append(r)
    
    unique_recommendations.sort(key=lambda x: x['confidence'], reverse=True)
    
    return unique_recommendations[:3]

@api_view(['POST'])
@csrf_exempt
def generate_graph(request):
    """Generate a graph with multiple graph type support and full color customization"""
    global uploaded_data

    if uploaded_data is None:
        return Response({"error": "No data uploaded yet"}, status=400)

    x_column = request.data.get('x_column')
    y_columns = request.data.get('y_columns', [])
    graph_type = request.data.get('graph_type', 'line')
    custom_colors = request.data.get('colors', [])
    color_all = request.data.get('color_all', False)
    download = request.data.get('download', False)

    if not isinstance(y_columns, list) or len(y_columns) == 0:
        return Response({"error": "Please provide a list of Y-axis columns"}, status=400)

    if x_column not in uploaded_data.columns:
        return Response({"error": "Invalid X-axis column selection"}, status=400)

    for y_col in y_columns:   
        if y_col not in uploaded_data.columns:
            return Response({"error": f"Invalid Y-axis column: {y_col}"}, status=400)

    try:
        plt.style.use('seaborn-v0_8')
    except:
        try:
            plt.style.use('seaborn')
        except:
            sns.set_style("whitegrid")

    plt.figure(figsize=(10, 6))
    
    if color_all and custom_colors:
        colors = [custom_colors[0]] * len(y_columns)
    elif custom_colors and len(custom_colors) >= len(y_columns):
        colors = custom_colors[:len(y_columns)]
    else:
        colors = sns.color_palette("tab10", n_colors=len(y_columns))

    try:
        if graph_type == 'line':
            for i, y_col in enumerate(y_columns):
                plt.plot(uploaded_data[x_column], uploaded_data[y_col], 
                        color=colors[i], 
                        marker='o' if len(y_columns) < 5 else '', 
                        linewidth=2, 
                        label=y_col)

        elif graph_type == 'bar':
            width = 0.8 / len(y_columns)
            x_values = range(len(uploaded_data[x_column]))

            for i, y_col in enumerate(y_columns):
                plt.bar([x + i * width for x in x_values], 
                        uploaded_data[y_col], 
                        width=width, 
                        color=colors[i], 
                        alpha=0.8,
                        label=y_col)

            plt.xticks([x + (len(y_columns)-1)*width/2 for x in x_values], 
                       uploaded_data[x_column])

        elif graph_type == 'pie':
            if len(y_columns) > 1:
                return Response({"error": "Pie chart supports only one Y column"}, status=400)
            
            y_col = y_columns[0]
            numeric_values = pd.to_numeric(uploaded_data[y_col], errors='coerce')
            mask = ~numeric_values.isna()

            if not mask.any():
                return Response({"error": "Y-axis column must contain numeric values for pie chart."}, status=400)

            plt.pie(numeric_values[mask], 
                    labels=uploaded_data[x_column][mask], 
                    autopct='%1.1f%%',
                    colors=colors[:len(uploaded_data[x_column][mask])],
                    startangle=90,
                    wedgeprops={'linewidth': 1, 'edgecolor': 'white'})

        elif graph_type == 'area':
            for i, y_col in enumerate(y_columns):
                plt.fill_between(uploaded_data[x_column], 
                               uploaded_data[y_col], 
                               color=colors[i], 
                               alpha=0.4,
                               label=y_col)
                plt.plot(uploaded_data[x_column], 
                        uploaded_data[y_col], 
                        color=colors[i], 
                        alpha=0.8,
                        linewidth=1)

        elif graph_type == 'scatter':
            for i, y_col in enumerate(y_columns):
                plt.scatter(uploaded_data[x_column], 
                          uploaded_data[y_col], 
                          color=colors[i], 
                          s=100,
                          alpha=0.7,
                          label=y_col)

        elif graph_type == 'histogram':
            for i, y_col in enumerate(y_columns):
                plt.hist(uploaded_data[y_col], 
                        bins='auto', 
                        color=colors[i], 
                        alpha=0.7,
                        label=y_col)

        elif graph_type == 'box':
            data_to_plot = [uploaded_data[col] for col in y_columns]
            box = plt.boxplot(data_to_plot, 
                            patch_artist=True,
                            labels=y_columns)
            
            for patch, color in zip(box['boxes'], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)

        elif graph_type == 'violin':
            data_to_plot = [uploaded_data[col] for col in y_columns]
            violin = plt.violinplot(data_to_plot,
                                  showmeans=True,
                                  showmedians=True)
            
            for patch, color in zip(violin['bodies'], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)

            plt.xticks(range(1, len(y_columns)+1), y_columns)

        elif graph_type == 'funnel':
            y_col = y_columns[0]
            plt.barh(uploaded_data[x_column], 
                    uploaded_data[y_col], 
                    color=colors[:len(uploaded_data[x_column])])
            plt.gca().invert_yaxis()

        elif graph_type == 'sunburst':
            if len(y_columns) != 1:
                return Response({"error": "Sunburst chart needs exactly one Y column"}, status=400)
            
            y_col = y_columns[0]
            numeric_values = pd.to_numeric(uploaded_data[y_col], errors='coerce')
            mask = ~numeric_values.isna()

            if not mask.any():
                return Response({"error": "Y-axis column must contain numeric values for sunburst chart."}, status=400)

            plt.pie(numeric_values[mask], 
                    labels=uploaded_data[x_column][mask], 
                    autopct='%1.1f%%',
                    colors=colors[:len(uploaded_data[x_column][mask])],
                    startangle=90,
                    wedgeprops=dict(width=0.5, edgecolor='w'))

        elif graph_type == 'waterfall':
            y_col = y_columns[0]
            values = uploaded_data[y_col].cumsum()
            plt.bar(uploaded_data[x_column], 
                   uploaded_data[y_col], 
                   bottom=values - uploaded_data[y_col],
                   color=colors[:len(uploaded_data[x_column])])

        elif graph_type == 'combo':
            if len(y_columns) < 2:
                return Response({"error": "Combo chart needs at least 2 Y columns"}, status=400)
            
            plt.bar(uploaded_data[x_column], 
                   uploaded_data[y_columns[0]], 
                   color=colors[0],
                   alpha=0.7,
                   label=y_columns[0])
            
            plt.plot(uploaded_data[x_column], 
                   uploaded_data[y_columns[1]], 
                   color=colors[1],
                   marker='o',
                   linewidth=2,
                   label=y_columns[1])
            
            if len(y_columns) > 2:
                markers = ['s', '^', 'D', 'v', 'p', '*']
                for i in range(2, len(y_columns)):
                    plt.plot(uploaded_data[x_column], 
                           uploaded_data[y_columns[i]], 
                           color=colors[i],
                           marker=markers[(i-2) % len(markers)],
                           linewidth=2,
                           label=y_columns[i])

        elif graph_type == 'stock':
            if len(y_columns) < 4:
                return Response({"error": "Stock chart requires Open, High, Low, Close columns"}, status=400)
            
            try:
                timeframe = request.data.get('timeframe', '1D').upper()
                
                df = uploaded_data.copy()
                df[x_column] = pd.to_datetime(df[x_column])
                
                for col in y_columns[:4]:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df = df.set_index(x_column).sort_index()
                df = df.dropna(subset=y_columns[:4])
                
                timeframe_map = {
                    '1M': '1T',    
                    '5M': '5T',    
                    '10M': '10T',   
                    '15M': '15T',   
                    '30M': '30T',   
                    '1H': '1H',  
                    '4H': '4H',    
                    '1D': '1D',    
                    '1W': '1W',  
                    '1MO': '1M'     
                }
                
                if timeframe not in timeframe_map:
                    return Response({"error": "Invalid timeframe. Use 1M,5M,10M,15M,30M,1H,4H,1D,1W,1MO"}, status=400)
                
                ohlc_dict = {
                    y_columns[0]: 'first',  
                    y_columns[1]: 'max',    
                    y_columns[2]: 'min',    
                    y_columns[3]: 'last',   
                }
                
                if len(y_columns) > 4:
                    ohlc_dict[y_columns[4]] = 'sum'
                
                resampled_df = df.resample(timeframe_map[timeframe]).agg(ohlc_dict).dropna()
                
                resampled_df['date_num'] = mdates.date2num(resampled_df.index)
                ohlc_columns = ['date_num'] + y_columns[:4]
                ohlc = resampled_df[ohlc_columns].values
                
                plt.close('all')
                fig, ax = plt.subplots(figsize=(15, 7))
                
                candlestick_ohlc(ax, ohlc, width=0.6/len(timeframe_map[timeframe]), 
                                colorup='g', colordown='r')
                
                ax.xaxis_date()
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
                plt.xticks(rotation=45)
                ax.set_title(f'Stock Price ({timeframe} timeframe)')
                ax.set_xlabel('Date/Time')
                ax.set_ylabel('Price')
                
                if len(y_columns) > 4:
                    ax2 = ax.twinx()
                    ax2.bar(resampled_df.index, resampled_df[y_columns[4]], 
                        width=0.01, alpha=0.3, color='blue')
                    ax2.set_ylabel('Volume', color='blue')
                
                plt.tight_layout()
                
            except Exception as e:
                plt.close('all')
                return Response({"error": f"Failed to generate stock chart: {str(e)}"}, status=400)

        if graph_type != 'stock':
            plt.xlabel(x_column, fontsize=12)
            plt.ylabel("Values", fontsize=12)
            plt.title(f"{graph_type.capitalize()} Chart", fontsize=14)
            
            if graph_type not in ['pie', 'sunburst', 'funnel']:
                plt.legend(fontsize=10, bbox_to_anchor=(1.05, 1), loc='upper left')
                plt.grid(True, linestyle='--', alpha=0.7)

        plt.tight_layout()

        if download:
            # For download, return the image file directly
            buffer = BytesIO()
            plt.savefig(buffer, format="png", dpi=300)  # Higher DPI for better quality
            buffer.seek(0)
            plt.close()
            
            response = HttpResponse(buffer.getvalue(), content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="{graph_type}_chart.png"'
            return response
        else:
            # For normal display in the UI
            buffer = BytesIO()
            plt.savefig(buffer, format="png", dpi=120)
            buffer.seek(0)
            encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
            buffer.close()
            plt.close()

            return Response({
                "graph": encoded_image,
                "graph_type": graph_type,
                "colors_used": colors[:len(y_columns)]
            })

    except Exception as e:
        plt.close()
        return Response({"error": f"Graph generation failed: {str(e)}"}, status=500)

@api_view(['POST'])
@csrf_exempt
def download_graph(request):
    """Endpoint specifically for downloading graphs"""
    request.data['download'] = True
    return generate_graph(request)