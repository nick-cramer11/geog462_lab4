import arcpy
import pandas as pd
import math
import matplotlib.pyplot as plt


class SmartRaster(arcpy.Raster):

    def __init__(self, raster_path):
        super().__init__(raster_path)
        self.raster_path = raster_path
        self.metadata = self._extract_metadata()

    def _extract_metadata(self):
        desc = arcpy.Describe(self.raster_path)
        extent = desc.extent
        
        bounds = [[extent.XMin, extent.YMax],
                  [extent.XMax, extent.YMin]]

        y_dim = self.height
        x_dim = self.width
        n_bands = self.bandCount
        pixelType = self.pixelType

        return {
            "bounds":bounds, 
            "x_dim": x_dim, 
            "y_dim": y_dim, 
            "n_bands": n_bands, 
            "pixelType": pixelType
        }

    def calculate_ndvi(self,  band4_index = 4, band3_index = 3):

        """Calculate NDVI using the NIR and Red bands."""
       
        # Indicator about whether things work
        okay = True

        try:
            # Load the NIR and Red bands
            nir = arcpy.Raster(self.raster_path + f"/Band_{band4_index}")
            red = arcpy.Raster(self.raster_path + f"/Band_{band3_index}")

            from arcpy.sa import Divide, Float, Minus, Plus

            # Calculate NDVI = (NIR - Red) / (NIR + Red)
            numerator = Float(nir - red)
            denominator = Float(nir + red)

            ndvi = Divide(numerator, denominator)

            return okay, ndvi

        except Exception as e:
            okay = False
            return okay, e




# Potential smart vector layer

class SmartVectorLayer:
    def __init__(self, feature_class_path):
        """Initialize with a path to a vector feature class"""
        self.feature_class = feature_class_path
        
        # Check if it exists
        if not arcpy.Exists(self.feature_class):
            raise FileNotFoundError(f"{self.feature_class} does not exist.")
    def summarize_field(self, field):
        # set up a tracking variable to track if things work
        okay = True

        #check if the field is in the legit list
        try: 
            existing_fields = [f.name for f in arcpy.ListFields(self.feature_class)]
            if field not in existing_fields:
                okay = False
                print(f"The field {field} is not in list of possible fields")
                return False, None
        except Exception as e:
            print(f"Problem checking the fields: {e}")

        # now go through and get the mean value
        try: 
            with arcpy.da.SearchCursor(self.feature_class, [field]) as cursor:
                vals = [row[0] for row in cursor if row[0] is not None and not math.isnan(row[0])]
            mean = sum(vals)/len(vals)
            return okay, mean
        except Exception as e:
            print(f"Problem calculating mean: {e}")
            okay = False
            return okay, None

    
    def zonal_stats_to_field(self, raster_path, statistic_type="MEAN", output_field="ZonalStat"):
        """
        For each feature in the vector layer, calculates the zonal statistic from the raster
        and writes it to a new field.
        """
        okay = True

        # Step 1: Add output field (if it does not exist)
        try:
            existing_fields = [f.name for f in arcpy.ListFields(self.feature_class)]
            if output_field in existing_fields:
                print(f"Field {output_field} already exists. Aborting field creation.")
            else:
                arcpy.management.AddField(self.feature_class, output_field, "DOUBLE")
        except Exception as e:
            print(f"Error adding field {output_field}: {e}")
            okay = False
            return okay

        # Step 2: Calculate zonal statistics
        temp_table = "in_memory\\temp_zonal_stats"
        if arcpy.Exists(temp_table):
            arcpy.management.Delete(temp_table)

        try:
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data=self.feature_class,
                zone_field="OBJECTID",
                in_value_raster=raster_path,
                out_table=temp_table,
                statistics_type=statistic_type
            )
        except Exception as e:
            print(f"Problem calculating zonal statistics: {e}")
            okay = False
            return okay

        # Step 3: Read results into a dictionary
        zonal_results = {}
        try:
            with arcpy.da.SearchCursor(temp_table, ["OBJECTID_1", statistic_type]) as cursor:
                for row in cursor:
                    zonal_results[row[0]] = row[1]
        except Exception as e:
            print(f"Problem reading the zonal results table: {e}")
            okay = False
            return okay

        # Step 4: Update feature class with results
        try:
            with arcpy.da.UpdateCursor(self.feature_class, ["OBJECTID", output_field]) as cursor:
                for row in cursor:
                    obj_id = row[0]
                    if obj_id in zonal_results:
                        row[1] = zonal_results[obj_id]
                        cursor.updateRow(row)
        except Exception as e:
            print(f"Problem updating the feature class: {e}")
            okay = False
            return okay

        # Step 5: Clean up
        arcpy.management.Delete(temp_table)

        print(f"Zonal stats '{statistic_type}' added to field '{output_field}'.")
        return okay

    
    def save_as(self, output_path):
        """Save the current vector layer to a new feature class"""
        arcpy.management.CopyFeatures(self.feature_class, output_path)
        print(f"Saved to {output_path}")


    # Take our vector object and turn it into a pandas dataframe

    def extract_to_pandas_df(self, fields=None):
        # set up tracker variable
        okay = True

        #First, get the list of fields to extract if the user did 
        #  not pass them

        if fields is None: # If the user did not pass anything
            # List all field names (excluding geometry)
            fields = [f.name for f in arcpy.ListFields(self.feature_class) if f.type not in ('Geometry', 'OID')]
        else: 
            #check to make sure that the fields given are actually in the table, 
            #   and make sure to exclue the geometry and oid.

            true_fields = [f.name for f in arcpy.ListFields(self.feature_class) if f.type not in ('Geometry', 'OID')]

            #accumulate the ones that do not match
            disallowed = [user_f for user_f in fields if user_f not in true_fields]

            # if the list is not empty, let the user know
            if len(disallowed) != 0:
                print("Fields given by user are not valid for this table")
                print(disallowed)
                okay = False
                return okay, None
        
        # Step 2: Create a search cursor and extract rows
        try:
            with arcpy.da.SearchCursor(self.feature_class, fields) as cursor:
                rows = [row for row in cursor]
        except Exception as e:
            print(f"Problem extracting rows: {e}")
            okay = False
            return okay, None

        # Step 3: Convert to pandas DataFrame
        df = pd.DataFrame(rows, columns=fields)
                
        return okay, df


# Uncomment this when you get to the appropriate block in the scripts
#  file and re-load the functions

# class smartPanda(pd.DataFrame):

#     # This next bit is advanced -- don't worry about it unless you're 
#     # curious.  It has to do with the pandas dataframe
#     # being a complicated thing that could be created from a variety
#     #   of types, and also that it creates a new dataframe
#     #   when it does operations.  The use of @property is called
#     #   a "decorator".  The _constructor(self) is a specific 
#     #   expectation of Pandas when it does operations.  This just
#     #   tells it that when it does an operation, make the new thing
#     #   into a special smartPanda type, not an original dataframe. 

#     @property
#     def _constructor(self):
#         return smartPanda
    
#     # here, just set up a method to plot and to allow
#     #   the user to define the min and max of the plot. 


#     def scatterplot(self, x_field, y_field, title=None, 
#                     x_min=None, x_max=None, 
#                     y_min=None, y_max=None):
#         """Make a scatterplot of two columns, with validation."""

#         # Validate
#         for field in [x_field, y_field]:
#             if field not in self.columns:
#                 raise ValueError(f"Field '{field}' not found in DataFrame columns.")

#         # filter the range
#         df_to_plot = self
#         if x_min is not None:
#             df_to_plot = df_to_plot[df_to_plot[x_field] >= x_min]
#         if x_max is not None:
#             df_to_plot = df_to_plot[df_to_plot[x_field] <= x_max]
#         if y_min is not None:
#             df_to_plot = df_to_plot[df_to_plot[y_field] >= y_min]
#         if y_max is not None:
#             df_to_plot = df_to_plot[df_to_plot[y_field] <= y_max]



#         # Proceed to plot
#         plt.figure(figsize=(8,6))
#         plt.scatter(df_to_plot[x_field], df_to_plot[y_field])
#         plt.xlabel(x_field)
#         plt.ylabel(y_field)
#         plt.title(title if title else f"{y_field} vs {x_field}")
#         plt.grid(True)
#         plt.show()


#     def mean_field(self, field):
#         """Get mean of a field, ignoring NaN."""
#         return self[field].mean(skipna=True)

#     def save_scatterplot(self, x_field, y_field, outfile, title=None, 
#                     x_min=None, x_max=None, 
#                     y_min=None, y_max=None):
#         """Make a scatterplot of two columns, with validation."""

#         # Validate
#         for field in [x_field, y_field]:
#             if field not in self.columns:
#                 raise ValueError(f"Field '{field}' not found in DataFrame columns.")

#         # filter the range
#         df_to_plot = self
#         if x_min is not None:
#             df_to_plot = df_to_plot[df_to_plot[x_field] >= x_min]
#         if x_max is not None:
#             df_to_plot = df_to_plot[df_to_plot[x_field] <= x_max]
#         if y_min is not None:
#             df_to_plot = df_to_plot[df_to_plot[y_field] >= y_min]
#         if y_max is not None:
#             df_to_plot = df_to_plot[df_to_plot[y_field] <= y_max]



#         # Proceed to plot
#         plt.figure(figsize=(8,6))
#         plt.scatter(df_to_plot[x_field], df_to_plot[y_field])
#         plt.xlabel(x_field)
#         plt.ylabel(y_field)
#         plt.title(title if title else f"{y_field} vs {x_field}")
#         plt.grid(True)
#         plt.savefig(outfile)
#         plt.close()

#     def plot_from_file(self, csv_control_file_path):
#         #  This reads the file at csv_control_file_path
#         #   and uses it to make a plot, and then save
#         #   it.  

#         #  First, use the pandas functionality to read the
#         #    .csv file.  The file should have two columns:
#         #   param and value
#         #  the param is the name of the item of interest, for 
#         #    example "in_file", and the value is the value 
#         #    of that param. 
#         #  The required params are:
#         #     param   -> value type
#         #     --------------------
#         #     x_field -> string
#         #     y_field -> string
#         #     outfile -> string path to graphics file output
#         #  Optional:
#         #     x_min -> numeric
#         #     x_max -> numeric
#         #     y_min -> numeric
#         #     y_max -> numeric
             

#         try: 
#             params = pd.read_csv(csv_control_file_path)
#         except Exception as e:
#             print(f"Problem reading the {csv_control_file_path}")
#             return False
        
#         # Then we'll turn it into a dictionary
#         #  To do this, we'll use a new functionality that you'll
#         #  see in Python a lot -- "zip".   Look it up!  
#         # Also, you can see I'm doing a trick with the 
#         #  definition of the dictionary -- 
        
#         try:
#             param_dict ={k.strip(): v for k,v in zip(params['Param'], params['Value'])}

#         except Exception as e:
#             print(f"Problem setting up dictionary: {e}")

#         # Then check that the required params are present
#         # required params
#         required_params = ["x_field", "y_field", "outfile"]

#         #  Use a list comprehension and the .keys() to test 
#         #   if the required ones are in the dictionary

#         missing = [m for m in required_params if m not in param_dict.keys()]
#         if missing:
#             print("The param file needs to have these additional parameters")
#             print(missing)
#             return False


#         #  Now add in "None" vals for the 
#         #    optional params if the user does not set them


#         optional_params = ["x_min", "x_max", "y_min", "y_max"]
#         # go through the optional params, and if one is 
#         #   is not in the param_dict, add it but give it the 
#         #   value of "None" so the plotter won't set it. 

       
#         for p in optional_params:
#             if p not in param_dict.keys():
#                 param_dict[p] = None

#         # Finally, do the plot! 
#         try:
#             self.save_scatterplot(param_dict['x_field'], 
#                                param_dict['y_field'], 
#                                param_dict['outfile'], 
#                                x_min = param_dict['x_min'], 
#                                x_max = param_dict['x_max'],
#                                y_min = param_dict['y_min'],
#                                y_max = param_dict['y_max'])
#             print(f"wrote to {params}")
#             return True   # report back success
#         except Exception as e:
#             print(f"Problem saving the scatterplot: {e}")

        
            
        
        








