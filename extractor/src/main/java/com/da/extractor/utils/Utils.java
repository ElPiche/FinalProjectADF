package com.da.extractor.utils;


import java.io.IOException;
import java.util.Date;

public class Utils {

    /// Convierte un nombre de tipo de dato de Elasticsearch a su clase correspondiente
    /// @param className El nombre del tipo de dato de Elasticsearch
    /// @return La clase correspondiente al tipo de dato, puede ser del la libreria estándar de Java o
    /// o de la librería de <code>co.elastic.clients.util</code> de Elasticsearch
    public static Class<?> getClassFromString(String className) throws IOException {

        return switch (className){
//            case "string", "text" -> String.class;

//            case "long" -> Long.class;
            case "double",
                 "long",
                 "integer",
                 "float",
                 "half_float",
                 "scaled_float",
                 "unsigned_long",
                 "short" -> Double.class;

//            case "boolean" -> Boolean.class;

            case "datetime" -> Date.class;

            default -> throw new IOException("""
                   One of these happens:
                   1. One ore more selected dimensions field isn't numeric type.
                   2. Timestamp field isn't date type."""
            );
        };
    }

    public static String normalizeCron(String cron, long seconds){
        String[] parts = cron.trim().split("\\s+");
        return (parts.length == 5) ? seconds + " " + cron : cron;
    }
}
