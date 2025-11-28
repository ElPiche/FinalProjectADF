package com.da.extractor.utils;


import java.util.Date;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Utils {

    /// Convierte un nombre de tipo de dato de Elasticsearch a su clase correspondiente
    /// @param className El nombre del tipo de dato de Elasticsearch
    /// @return La clase correspondiente al tipo de dato, puede ser del la libreria estándar de Java o
    /// o de la librería de <code>co.elastic.clients.util</code> de Elasticsearch
    public static Class<?> getClassFromString(String className) {

        return switch (className){
            case "string", "text" -> String.class;
//            case "long" -> Long.class;
            case "double", "long" -> Double.class;
            case "boolean" -> Boolean.class;
            case "datetime" -> Date.class;
            default -> Object.class;
        };
    }

    /// Extrae el nombre del índice de una consulta Elasticsearch SQL
    public static String extractIndexName(String query) {
        Pattern pattern = Pattern.compile(
                "FROM\\s+\"?([a-zA-Z0-9_.\\-*]+)\"?",
                Pattern.CASE_INSENSITIVE
        );
        Matcher matcher = pattern.matcher(query);
        if (matcher.find()) {
            return matcher.group(1);
        }
        return null;
    }

}
